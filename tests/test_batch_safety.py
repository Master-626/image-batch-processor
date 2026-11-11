"""Disposable synthetic images exercise the legacy API and CLI file-safety contract."""

import hashlib
import os
from pathlib import Path
from unittest.mock import Mock

import pytest
from click.testing import CliRunner
from PIL import Image

from image_batch_processor import BatchProcessor, BatchSafetyError, ProcessOptions
from image_batch_processor.cli import main
from image_batch_processor.core import _is_link, _portable_name, _walk_error


def image(path, color='red'):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new('RGB', (16, 16), color).save(path)
    return path


def hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file() and not p.is_symlink()}


@pytest.fixture
def batch(tmp_path):
    source = tmp_path / 'input'
    image(source / 'sample.jpg')
    image(source / 'sample.png', 'blue')
    return source, tmp_path / 'output'


def test_same_stem_collision_fails_before_any_write(batch):
    source, output = batch
    image(source / 'aaa.jpg', 'green')  # Would be written first in an incremental check.
    before = hashes(source)
    with pytest.raises(BatchSafetyError, match='collision'):
        BatchProcessor(ProcessOptions(output_format='webp')).process_directory(source, output)
    assert not output.exists()
    assert hashes(source) == before


def test_cli_collision_is_nonzero_without_outputs(batch):
    source, output = batch
    result = CliRunner().invoke(main, [str(source), '-o', str(output), '--format', 'webp'])
    assert result.exit_code != 0 and 'collision' in result.output
    assert not output.exists()


def test_existing_target_blocks_the_entire_batch(tmp_path):
    source, output = tmp_path / 'input', tmp_path / 'output'
    image(source / 'aaa.jpg')
    image(source / 'zzz.png')
    output.mkdir()
    (output / 'zzz.webp').write_bytes(b'keep existing bytes')
    before = hashes(output)
    with pytest.raises(BatchSafetyError, match='already exists'):
        BatchProcessor(ProcessOptions(output_format='webp')).process_directory(source, output)
    assert hashes(output) == before


def test_existing_directory_with_unrelated_files_is_allowed(tmp_path):
    source, output = tmp_path / 'input', tmp_path / 'output'
    image(source / 'one.png')
    output.mkdir()
    (output / 'notes.txt').write_bytes(b'keep')
    result = BatchProcessor(ProcessOptions(output_format='webp')).process_directory(source, output)
    assert result == {'total': 1, 'success': 1, 'failed': 0}
    assert (output / 'notes.txt').read_bytes() == b'keep'
    with Image.open(output / 'one.webp') as exported:
        assert exported.format == 'WEBP'


@pytest.mark.parametrize('kind', ['same', 'relative-alias', 'nested', 'ancestor', 'case-alias'])
def test_overlapping_directory_aliases_are_rejected(batch, monkeypatch, kind):
    source, output = batch
    monkeypatch.chdir(source.parent)
    destinations = {'same': source, 'relative-alias': Path('input') / '..' / 'input',
                    'nested': source / 'new', 'ancestor': source.parent,
                    'case-alias': source.with_name('INPUT')}
    before = hashes(source)
    with pytest.raises(BatchSafetyError, match='non-overlapping'):
        BatchProcessor(ProcessOptions(scale=.5)).process_directory(source, destinations[kind])
    assert hashes(source) == before


def test_output_root_symlink_alias_is_rejected(batch):
    source, output = batch
    try:
        output.symlink_to(source, target_is_directory=True)
    except OSError:
        pytest.skip('symlink creation unavailable')
    before = hashes(source)
    with pytest.raises(BatchSafetyError, match='symbolic links'):
        BatchProcessor(ProcessOptions(scale=.5)).process_directory(source, output)
    assert hashes(source) == before


def test_existing_symlinked_child_directory_rejected(tmp_path):
    source, output, unrelated = tmp_path / 'input', tmp_path / 'output', tmp_path / 'elsewhere'
    image(source / 'sub' / 'one.png')
    output.mkdir(); unrelated.mkdir()
    try:
        (output / 'sub').symlink_to(unrelated, target_is_directory=True)
    except OSError:
        pytest.skip('symlink creation unavailable')
    with pytest.raises(BatchSafetyError, match='symbolic link'):
        BatchProcessor(ProcessOptions(output_format='webp')).process_directory(source, output, recursive=True)
    assert list(unrelated.iterdir()) == []


def test_broken_output_symlink_is_preserved(tmp_path):
    source, output = tmp_path / 'input', tmp_path / 'output'
    image(source / 'one.png'); output.mkdir()
    link = output / 'one.webp'
    try:
        link.symlink_to(tmp_path / 'missing')
    except OSError:
        pytest.skip('symlink creation unavailable')
    with pytest.raises(BatchSafetyError, match='symbolic link'):
        BatchProcessor(ProcessOptions(output_format='webp')).process_directory(source, output)
    assert link.is_symlink() and not (tmp_path / 'missing').exists()


def test_same_file_direct_api_preserves_original(tmp_path):
    source = image(tmp_path / 'one.png')
    before = source.read_bytes()
    assert not BatchProcessor(ProcessOptions(scale=.5)).process_file(source, source)
    assert source.read_bytes() == before


def test_existing_hardlink_direct_api_preserves_both_names(tmp_path):
    source = image(tmp_path / 'one.png')
    output = tmp_path / 'hardlink.png'
    try:
        os.link(source, output)
    except OSError:
        pytest.skip('hardlinks unavailable')
    before = source.read_bytes()
    assert not BatchProcessor(ProcessOptions(scale=.5)).process_file(source, output)
    assert source.read_bytes() == before and output.read_bytes() == before


def test_case_folded_batch_name_collision(tmp_path):
    source, output = tmp_path / 'input', tmp_path / 'output'
    image(source / 'Example.jpg'); image(source / 'example.png')
    with pytest.raises(BatchSafetyError, match='collision'):
        BatchProcessor(ProcessOptions(output_format='webp')).process_directory(source, output)
    assert not output.exists()


def test_unicode_normalized_batch_name_collision(tmp_path):
    source, output = tmp_path / 'input', tmp_path / 'output'
    image(source / 'caf\u00e9.jpg'); image(source / 'cafe\u0301.png')
    with pytest.raises(BatchSafetyError, match='collision'):
        BatchProcessor(ProcessOptions(output_format='webp')).process_directory(source, output)
    assert not output.exists()


def test_existing_case_alias_is_preserved(tmp_path):
    source, output = tmp_path / 'input', tmp_path / 'output'
    image(source / 'one.png'); output.mkdir()
    (output / 'ONE.WEBP').write_bytes(b'keep')
    with pytest.raises(BatchSafetyError, match='alias|already exists'):
        BatchProcessor(ProcessOptions(output_format='webp')).process_directory(source, output)
    assert hashes(output) == {'ONE.WEBP': hashlib.sha256(b'keep').hexdigest()}


def test_recursive_file_directory_collision(tmp_path):
    source, output = tmp_path / 'input', tmp_path / 'output'
    image(source / 'sub.png'); image(source / 'sub.webp' / 'one.jpg')
    with pytest.raises(BatchSafetyError, match='collision'):
        BatchProcessor(ProcessOptions(output_format='webp')).process_directory(source, output, recursive=True)
    assert not output.exists()


def test_recursive_existing_file_cannot_become_directory(tmp_path):
    source, output = tmp_path / 'input', tmp_path / 'output'
    image(source / 'sub' / 'one.png'); output.mkdir(); (output / 'sub').write_bytes(b'keep')
    with pytest.raises(BatchSafetyError, match='not a directory'):
        BatchProcessor(ProcessOptions(output_format='webp')).process_directory(source, output, recursive=True)
    assert (output / 'sub').read_bytes() == b'keep'


def test_recursive_case_aliased_directory_names(tmp_path):
    source, output = tmp_path / 'input', tmp_path / 'output'
    image(source / 'Sub' / 'one.jpg'); image(source / 'sub' / 'two.png')
    if len(list(source.iterdir())) != 2:
        pytest.skip('filesystem already folds directory case')
    with pytest.raises(BatchSafetyError, match='collision'):
        BatchProcessor(ProcessOptions(output_format='webp')).process_directory(source, output, recursive=True)
    assert not output.exists()


def test_recursive_success_and_non_recursive_selection(tmp_path):
    source = tmp_path / 'input'
    image(source / 'one.png'); image(source / 'sub' / 'two.jpg')
    processor = BatchProcessor(ProcessOptions(output_format='webp'))
    assert processor.process_directory(source, tmp_path / 'flat')['total'] == 1
    assert processor.process_directory(source, tmp_path / 'recursive', recursive=True)['success'] == 2
    assert (tmp_path / 'recursive' / 'sub' / 'two.webp').is_file()


@pytest.mark.parametrize('name', ['CON.png', 'aux.jpg', 'COM1.webp', 'lpt9.png', 'COM¹.png',
                                  'bad:ads.png', 'folder.', 'folder ', 'line\n.png'])
def test_nonportable_names_are_rejected_on_every_platform(name):
    with pytest.raises(BatchSafetyError, match='not portable'):
        _portable_name(name)


@pytest.mark.parametrize('extension,expected', [('jpg', 'JPEG'), ('JPEG', 'JPEG'), ('tif', 'TIFF'),
                                               ('TIFF', 'TIFF'), ('WEBP', 'WEBP')])
def test_format_aliases_and_case(tmp_path, extension, expected):
    source, output = tmp_path / 'input', tmp_path / 'output'
    image(source / 'one.png')
    result = BatchProcessor(ProcessOptions(output_format=extension)).process_directory(source, output)
    assert result['success'] == 1
    with Image.open(output / ('one.' + extension.lower())) as result:
        assert result.format == expected


@pytest.mark.parametrize('value', ['', '../png', 'unsupported', 1])
def test_invalid_output_format_never_creates_files(batch, value):
    source, output = batch
    with pytest.raises(BatchSafetyError, match='Unsupported output format'):
        BatchProcessor(ProcessOptions(output_format=value)).process_directory(source, output)
    assert not output.exists()


def test_decode_failure_cli_reports_nonzero_and_keeps_success(tmp_path):
    source, output = tmp_path / 'input', tmp_path / 'output'
    image(source / 'aaa.png'); (source / 'zzz.png').write_bytes(b'broken')
    result = CliRunner().invoke(main, [str(source), '-o', str(output)])
    assert result.exit_code != 0
    assert 'Success: 1, Failed: 1' in result.output
    assert (output / 'aaa.png').is_file() and not (output / 'zzz.png').exists()


def test_cli_rejects_zero_width_and_bad_quality(tmp_path):
    source = tmp_path / "input"
    image(source / "a.png")
    output = tmp_path / "output"
    runner = CliRunner()
    width = runner.invoke(main, [str(source), "-o", str(output), "-w", "0"])
    quality = runner.invoke(main, [str(source), "-o", str(output), "-q", "0"])
    assert width.exit_code != 0 and quality.exit_code != 0
    assert not output.exists()


def test_empty_cli_is_nonzero(tmp_path):
    source = tmp_path / 'empty'; source.mkdir()
    result = CliRunner().invoke(main, [str(source), '-o', str(tmp_path / 'out')])
    assert result.exit_code != 0 and 'No supported image' in result.output
    assert not (tmp_path / 'out').exists()


def test_output_created_after_preflight_is_not_replaced(tmp_path, monkeypatch):
    source = image(tmp_path / 'one.png'); output = tmp_path / 'out.png'
    original_open = Path.open
    def racing_open(path, mode='r', *args, **kwargs):
        if path == output and mode == 'xb':
            with original_open(path, 'wb') as handle:
                handle.write(b'other process output')
        return original_open(path, mode, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', racing_open)
    assert not BatchProcessor(ProcessOptions()).process_file(source, output)
    assert output.read_bytes() == b'other process output'


@pytest.mark.parametrize('failure', [OSError('disk full'), KeyboardInterrupt()])
def test_interrupted_write_cleans_only_new_output(tmp_path, monkeypatch, failure):
    source = image(tmp_path / 'one.png'); output = tmp_path / 'out.png'
    before = source.read_bytes(); original_open = Path.open
    class BrokenWriter:
        def __init__(self, handle): self.handle = handle
        def __enter__(self): return self
        def __exit__(self, *args): self.handle.close()
        def fileno(self): return self.handle.fileno()
        def write(self, data):
            self.handle.write(data[:5]); self.handle.flush(); raise failure
    def fail_write(path, mode='r', *args, **kwargs):
        handle = original_open(path, mode, *args, **kwargs)
        return BrokenWriter(handle) if path == output and mode == 'xb' else handle
    monkeypatch.setattr(Path, 'open', fail_write)
    processor = BatchProcessor(ProcessOptions())
    if isinstance(failure, KeyboardInterrupt):
        with pytest.raises(KeyboardInterrupt): processor.process_file(source, output)
    else:
        assert not processor.process_file(source, output)
    assert not output.exists() and source.read_bytes() == before


def test_encode_error_creates_no_output(tmp_path, monkeypatch):
    source = image(tmp_path / 'one.png'); output = tmp_path / 'new' / 'out.png'
    def fail_save(*args, **kwargs): raise OSError('encoder failed')
    monkeypatch.setattr(Image.Image, 'save', fail_save)
    assert not BatchProcessor(ProcessOptions()).process_file(source, output)
    assert not output.parent.exists()


def test_windows_reparse_points_are_identified_without_windows():
    path = Mock()
    path.lstat.return_value = Mock(st_mode=0o40755, st_file_attributes=0x400)
    assert _is_link(path)


def test_walk_permission_errors_are_not_silently_ignored():
    with pytest.raises(PermissionError):
        _walk_error(PermissionError('cannot read folder'))


def test_parent_link_added_after_planning_does_not_escape_output(tmp_path, monkeypatch):
    source, output, elsewhere = tmp_path / 'input', tmp_path / 'output', tmp_path / 'elsewhere'
    image(source / 'sub' / 'one.png'); output.mkdir(); elsewhere.mkdir()
    # First establish that this host permits directory symlinks.
    probe = tmp_path / 'probe'
    try:
        probe.symlink_to(elsewhere, target_is_directory=True); probe.unlink()
    except OSError:
        pytest.skip('symlink creation unavailable')
    processor = BatchProcessor(ProcessOptions())
    original_plan = processor._plan_directory
    def swap_after_plan(*args):
        plan = original_plan(*args)
        (output / 'sub').symlink_to(elsewhere, target_is_directory=True)
        return plan
    monkeypatch.setattr(processor, '_plan_directory', swap_after_plan)
    result = processor.process_directory(source, output, recursive=True)
    assert result == {'total': 1, 'success': 0, 'failed': 1}
    assert list(elsewhere.iterdir()) == []


def test_interrupt_during_initial_ownership_check_cleans_owned_file(tmp_path, monkeypatch):
    source = image(tmp_path / 'one.png'); output = tmp_path / 'out.png'
    original_fstat = os.fstat
    calls = 0
    def interrupt_once(fd):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise KeyboardInterrupt()
        return original_fstat(fd)
    monkeypatch.setattr(os, 'fstat', interrupt_once)
    with pytest.raises(KeyboardInterrupt):
        BatchProcessor(ProcessOptions()).process_file(source, output)
    assert not output.exists()
