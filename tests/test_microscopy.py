import csv
import hashlib
import json
import os
from dataclasses import replace

import numpy as np
import pytest
import tifffile
from click.testing import CliRunner
from PIL import Image

from image_batch_processor.microscopy import (
    ExportError,
    ExportSettings,
    export_batch,
    inspect_batch,
    replay_batch,
)
from image_batch_processor.microscopy_cli import main


@pytest.fixture
def source(tmp_path):
    root = tmp_path / 'input'
    root.mkdir()
    # Rows include 0, 100, 200, ..., 25500. Artificial data only.
    plane = np.tile(np.arange(256, dtype=np.uint16) * 100, (128, 1))
    tifffile.imwrite(root / 'synthetic.tif', plane, metadata={'axes': 'YX'})
    return root


@pytest.fixture
def settings():
    return ExportSettings(1000, 20000, 0.5, 20, synthetic_data=True)


def export(source, output, settings, **kwargs):
    return export_batch(source, output, settings, confirm_calibration=True, **kwargs)


def test_exact_pixels_hashes_crop_and_bar(source, tmp_path, settings):
    before = (source / 'synthetic.tif').read_bytes()
    result = export(source, tmp_path / 'out', replace(settings, crop=(10, 20, 200, 80)))
    assert (source / 'synthetic.tif').read_bytes() == before
    assert result['files'][0]['source_sha256'] == hashlib.sha256(before).hexdigest()
    record = result['files'][0]
    png_path = tmp_path / 'out' / record['output']
    assert record['output_sha256'] == hashlib.sha256(png_path.read_bytes()).hexdigest()
    with Image.open(png_path) as png:
        pixels = np.array(png)
        assert png.mode == 'L' and png.size == (200, 136)
    expected = np.floor(np.clip((np.arange(10, 210) * 100 - 1000) / 19000, 0, 1) * 255 + .5).astype(np.uint8)
    np.testing.assert_array_equal(pixels[:80], np.tile(expected, (80, 1)))
    x, y, w, h = record['scale_bar_xywh']
    assert w == 40 and h == 4
    assert np.count_nonzero(pixels[y]) == w
    assert np.all(pixels[y:y+h, x:x+w] == 255)
    assert record['clipped_low_pixels'] == 0
    assert record['clipped_high_pixels'] == 9 * 80
    assert record['scale_bar_label'] == '20 um'
    assert json.loads((tmp_path / 'out' / 'manifest.json').read_text())['settings']['crop'] == [10, 20, 200, 80]
    with (tmp_path / 'out' / 'manifest.csv').open(newline='') as handle:
        row = next(csv.DictReader(handle))
    assert row['source_sha256'] == record['source_sha256'] and row['pixel_size_um'] == '0.5'
    assert str(tmp_path) not in (tmp_path / 'out' / 'manifest.json').read_text()


def test_identical_replay(source, tmp_path, settings):
    export(source, tmp_path / 'first', settings)
    replay_batch(source, tmp_path / 'second', tmp_path / 'first' / 'manifest.json', confirm_calibration=True)
    for path in (tmp_path / 'first').iterdir():
        assert path.read_bytes() == (tmp_path / 'second' / path.name).read_bytes()


def test_replay_source_change_rolls_back(source, tmp_path, settings):
    export(source, tmp_path / 'first', settings)
    tifffile.imwrite(source / 'synthetic.tif', np.zeros((128, 256), dtype=np.uint16))
    with pytest.raises(ExportError, match='source hash differs'):
        replay_batch(source, tmp_path / 'bad', tmp_path / 'first' / 'manifest.json', confirm_calibration=True)
    assert not (tmp_path / 'bad').exists()


def test_replay_extra_file(source, tmp_path, settings):
    export(source, tmp_path / 'first', settings)
    (source / 'extra.tif').write_bytes((source / 'synthetic.tif').read_bytes())
    with pytest.raises(ExportError, match='input names differ'):
        replay_batch(source, tmp_path / 'bad', tmp_path / 'first' / 'manifest.json', confirm_calibration=True)
    assert not (tmp_path / 'bad').exists()


def test_replay_output_hash_mismatch(source, tmp_path, settings):
    export(source, tmp_path / 'first', settings)
    path = tmp_path / 'first' / 'manifest.json'
    manifest = json.loads(path.read_text())
    manifest['files'][0]['output_sha256'] = '0' * 64
    path.write_text(json.dumps(manifest))
    with pytest.raises(ExportError, match='PNG hash differs'):
        replay_batch(source, tmp_path / 'bad', path, confirm_calibration=True)
    assert not (tmp_path / 'bad').exists()


@pytest.mark.parametrize('changes', [
    {'display_min': 4, 'display_max': 4}, {'display_min': -1}, {'display_max': 65536},
    {'display_min': float('nan')}, {'display_max': float('inf')}, {'pixel_size_um': 0},
    {'scale_bar_um': -1}, {'scale_bar_um': .7}, {'pixel_size_um': 1e-320},
    {'crop': (-1, 0, 10, 10)}, {'crop': (0, 0, 0, 10)}, {'crop': (1.2, 0, 10, 10)},
    {'crop': (1, 2)}, {'synthetic_data': 'yes'}, {'display_min': True},
])
def test_invalid_settings(source, tmp_path, settings, changes):
    with pytest.raises(ExportError):
        export(source, tmp_path / 'out', replace(settings, **changes))
    assert not (tmp_path / 'out').exists()


def test_confirmation_required(source, tmp_path, settings):
    with pytest.raises(ExportError, match='Confirm'):
        export_batch(source, tmp_path / 'out', settings)
    assert not (tmp_path / 'out').exists()


@pytest.mark.parametrize('crop', [(200, 0, 200, 128), (0, 90, 200, 80), (0, 0, 10, 100)])
def test_bad_crop_rolls_back(source, tmp_path, settings, crop):
    with pytest.raises(ExportError):
        export(source, tmp_path / 'out', replace(settings, crop=crop))
    assert not (tmp_path / 'out').exists()


def test_existing_output_never_touched(source, tmp_path, settings):
    output = tmp_path / 'out'
    output.mkdir()
    (output / 'keep.txt').write_text('keep')
    with pytest.raises(ExportError, match='exists'):
        export(source, output, settings)
    assert (output / 'keep.txt').read_text() == 'keep'


@pytest.mark.parametrize('location', ['same', 'nested', 'ancestor'])
def test_overlapping_paths_rejected(source, tmp_path, settings, location):
    out = {'same': source, 'nested': source / 'out', 'ancestor': tmp_path}[location]
    with pytest.raises(ExportError, match='non-overlapping'):
        export(source, out, settings)


@pytest.mark.parametrize('kind', ['stack', 'rgb', 'signed', 'float', 'miniswhite', 'orientation', 'multiseries', 'ome_stack', 'pyramid'])
def test_unsupported_tiffs_rejected(source, tmp_path, settings, kind):
    path = source / 'unsupported.tif'
    image = np.zeros((128, 256), dtype=np.uint16)
    if kind == 'stack':
        tifffile.imwrite(path, np.stack([image, image]), photometric='minisblack')
    elif kind == 'rgb':
        tifffile.imwrite(path, np.zeros((128, 256, 3), dtype=np.uint8), photometric='rgb')
    elif kind == 'signed':
        tifffile.imwrite(path, image.astype(np.int16))
    elif kind == 'float':
        tifffile.imwrite(path, image.astype(np.float32))
    elif kind == 'miniswhite':
        tifffile.imwrite(path, image, photometric='miniswhite')
    elif kind == 'orientation':
        tifffile.imwrite(path, image, extratags=[(274, 'H', 1, 6, False)])
    elif kind == 'multiseries':
        with tifffile.TiffWriter(path) as writer:
            writer.write(image)
            writer.write(image[:64])
    elif kind == 'ome_stack':
        tifffile.imwrite(path, np.stack([image, image]), ome=True, metadata={'axes': 'ZYX'})
    elif kind == 'pyramid':
        with tifffile.TiffWriter(path) as writer:
            writer.write(image, subifds=1)
            writer.write(image[::2, ::2], subfiletype=1)
    with pytest.raises(ExportError):
        export(source, tmp_path / 'out', settings)
    assert not (tmp_path / 'out').exists()


def test_broken_file_rolls_back_prior_exports(source, tmp_path, settings):
    (source / 'zbroken.tif').write_bytes(b'not a TIFF')
    with pytest.raises(ExportError, match='cannot decode'):
        export(source, tmp_path / 'out', settings)
    assert not (tmp_path / 'out').exists()


def test_uint8_and_big_endian(tmp_path, settings):
    for dtype, maximum in [('uint8', 255), ('>u2', 65535)]:
        source = tmp_path / dtype.replace('>', 'big')
        source.mkdir()
        tifffile.imwrite(source / 'synthetic.tif', np.full((128, 256), maximum, dtype=dtype))
        result = export(source, source.with_name(source.name + '_out'), replace(settings, display_min=0, display_max=maximum))
        assert result['files'][0]['source_bit_depth'] == np.dtype(dtype).itemsize * 8


def test_tif_and_tiff_do_not_collide(source, tmp_path, settings):
    (source / 'synthetic.tiff').write_bytes((source / 'synthetic.tif').read_bytes())
    export(source, tmp_path / 'out', settings)
    assert (tmp_path / 'out' / 'synthetic.tif.png').exists()
    assert (tmp_path / 'out' / 'synthetic.tiff.png').exists()


def test_reject_symlink(source, tmp_path, settings):
    try:
        (source / 'link.tif').symlink_to(source / 'synthetic.tif')
    except OSError:
        pytest.skip('symlink creation unavailable')
    with pytest.raises(ExportError, match='symbolic link'):
        export(source, tmp_path / 'out', settings)


def test_non_recursive_and_empty_directory(tmp_path, settings):
    source = tmp_path / 'input'
    source.mkdir()
    (source / 'nested').mkdir()
    tifffile.imwrite(source / 'nested' / 'ignored.tif', np.zeros((128, 256), dtype=np.uint16))
    with pytest.raises(ExportError, match='No .tif'):
        export(source, tmp_path / 'out', settings)


def test_file_size_limit(source, tmp_path, settings, monkeypatch):
    monkeypatch.setattr('image_batch_processor.microscopy.MAX_FILE_BYTES', 100)
    with pytest.raises(ExportError, match='file exceeds'):
        export(source, tmp_path / 'out', settings)
    assert not (tmp_path / 'out').exists()


def test_pixel_limit(source, tmp_path, settings, monkeypatch):
    monkeypatch.setattr('image_batch_processor.microscopy.MAX_PIXELS', 100)
    with pytest.raises(ExportError, match='megapixel'):
        export(source, tmp_path / 'out', settings)


def test_csv_formula_name_rejected(source, tmp_path, settings):
    (source / '=formula.tif').write_bytes((source / 'synthetic.tif').read_bytes())
    with pytest.raises(ExportError, match='formula prefixes'):
        export(source, tmp_path / 'out', settings)


@pytest.mark.parametrize('bad', [{}, [], {'schema': 'other'}, {'schema': 'ibp-microscopy-export-v1', 'settings': {}, 'files': []}])
def test_bad_replay_manifest(source, tmp_path, bad):
    path = tmp_path / 'recipe.json'
    path.write_text(json.dumps(bad))
    with pytest.raises(ExportError):
        replay_batch(source, tmp_path / 'out', path, confirm_calibration=True)


def test_cli_export_replay_and_errors(source, tmp_path):
    runner = CliRunner()
    command = ['export', str(source), '-o', str(tmp_path / 'out'), '--display-min', '1000',
               '--display-max', '20000', '--pixel-size-um', '.5', '--scale-bar-um', '20', '--synthetic-data']
    assert runner.invoke(main, command).exit_code != 0
    result = runner.invoke(main, command + ['--confirm-calibration'])
    assert result.exit_code == 0, result.output
    replay = runner.invoke(main, ['replay', str(source), '-o', str(tmp_path / 'replayed'),
                                 '--manifest', str(tmp_path / 'out' / 'manifest.json'), '--confirm-calibration'])
    assert replay.exit_code == 0, replay.output
    duplicate = runner.invoke(main, command + ['--confirm-calibration'])
    assert duplicate.exit_code != 0 and 'already exists' in duplicate.output


def test_case_insensitive_collision(source, tmp_path, settings):
    (source / 'SYNTHETIC.TIF').write_bytes((source / 'synthetic.tif').read_bytes())
    if len(list(source.iterdir())) == 1:
        pytest.skip('filesystem is already case-insensitive')
    with pytest.raises(ExportError, match='case-insensitive'):
        export(source, tmp_path / 'out', settings)
    assert not (tmp_path / 'out').exists()


def test_mixed_bit_depth_range_rejected(source, tmp_path, settings):
    tifffile.imwrite(source / 'uint8.tif', np.zeros((128, 256), dtype=np.uint8))
    with pytest.raises(ExportError, match='bit-depth range'):
        export(source, tmp_path / 'out', settings)
    assert not (tmp_path / 'out').exists()


def test_output_parent_required(source, tmp_path, settings):
    with pytest.raises(ExportError, match='parent must already exist'):
        export(source, tmp_path / 'missing' / 'out', settings)


def test_unicode_normalized_tiff_names_collide(tmp_path, settings):
    source = tmp_path / "input"
    source.mkdir()
    plane = np.zeros((128, 256), dtype=np.uint16)
    tifffile.imwrite(source / "caf\u00e9.tif", plane)
    tifffile.imwrite(source / "cafe\u0301.tif", plane)
    if len(list(source.iterdir())) < 2:
        pytest.skip("filesystem already normalizes these filenames together")
    with pytest.raises(ExportError, match="Unicode-normalized"):
        export(source, tmp_path / "out", settings)
    assert not (tmp_path / "out").exists()


def test_reserved_windows_tiff_name_rejected(tmp_path, settings):
    if os.name == "nt":
        pytest.skip("creating a reserved device name is not safe on Windows")
    source = tmp_path / "input"
    source.mkdir()
    tifffile.imwrite(source / "CON.tif", np.zeros((128, 256), dtype=np.uint16))
    with pytest.raises(ExportError, match="not portable"):
        export(source, tmp_path / "out", settings)
    assert not (tmp_path / "out").exists()


def test_inspect_reports_geometry_without_writing(source, tmp_path, settings):
    before = {path.name: path.read_bytes() for path in source.iterdir()}
    report = inspect_batch(source, settings)
    assert {path.name: path.read_bytes() for path in source.iterdir()} == before
    assert list(tmp_path.rglob("*.png")) == []
    assert list(tmp_path.rglob("manifest.json")) == []
    assert report["file_count"] == 1
    assert report["scale_bar_pixels"] == 40
    assert report["scale_bar_label"] == "20 um"
    assert report["calibration"].startswith("not verified")
    record = report["files"][0]
    assert record["source"] == "synthetic.tif"
    assert record["source_sha256"] == hashlib.sha256(before["synthetic.tif"]).hexdigest()
    assert record["source_bit_depth"] == 16
    assert record["clipped_low_pixels"] == 10 * 128
    assert record["clipped_high_pixels"] == 55 * 128
    with pytest.raises(ExportError):
        inspect_batch(source, replace(settings, crop=(0, 0, 10, 100)))
    assert list(tmp_path.rglob("manifest.json")) == []


def test_cli_inspect_writes_nothing(source, tmp_path):
    result = CliRunner().invoke(main, [
        "inspect", str(source), "--display-min", "1000", "--display-max", "20000",
        "--pixel-size-um", "0.5", "--scale-bar-um", "20", "--synthetic-data",
    ])
    assert result.exit_code == 0, result.output
    assert "40 px" in result.output
    assert "synthetic.tif" in result.output
    assert "No files written" in result.output
    assert list(tmp_path.rglob("*.png")) == []
    bad = CliRunner().invoke(main, [
        "inspect", str(source), "--display-min", "4", "--display-max", "4",
        "--pixel-size-um", "0.5", "--scale-bar-um", "20",
    ])
    assert bad.exit_code != 0
    assert list(tmp_path.rglob("*.png")) == []


def test_zero_based_crop_half_up_rounding(source, tmp_path, settings):
    image = np.zeros((128, 256), dtype=np.uint16)
    image[:, 1] = 1
    image[:, 2] = 2
    tifffile.imwrite(source / 'synthetic.tif', image)
    result = export(source, tmp_path / 'out', replace(settings, display_min=0, display_max=2))
    with Image.open(tmp_path / 'out' / result['files'][0]['output']) as png:
        assert [png.getpixel((x, 0)) for x in range(3)] == [0, 128, 255]
