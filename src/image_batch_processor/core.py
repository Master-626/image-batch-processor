"""Sequential general-image processing with fail-closed output planning."""

import io
import os
import stat
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image

from .operations import resize_image, rotate_image, apply_text_watermark, convert_image_format


class BatchSafetyError(ValueError):
    """The batch has ambiguous or unsafe destinations; no processing has begun."""


def _is_link(path):
    """Include Windows junctions/reparse points as well as symbolic links."""
    try:
        info = path.lstat()
    except (FileNotFoundError, NotADirectoryError):
        return False
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _walk_error(error):
    raise error


def _name_key(name):
    """Use conservative Windows/macOS-style comparisons on every platform."""
    return unicodedata.normalize("NFC", name).casefold()


def _path_key(path):
    return tuple(_name_key(part) for part in path.parts)


def _overlap(left, right):
    a, b = _path_key(left), _path_key(right)
    return a[:len(b)] == b or b[:len(a)] == a


def _portable_name(name):
    # Reject names that may refer to a different path/device on Windows.
    devices = {"con", "prn", "aux", "nul", "conin$", "conout$"}
    devices.update("com" + str(i) for i in range(1, 10))
    devices.update("lpt" + str(i) for i in range(1, 10))
    devices.update(prefix + digit for prefix in ("com", "lpt") for digit in "¹²³")
    if (not name or name.endswith((".", " ")) or
            any(ord(char) < 32 or char in '<>:"/\\|?*' for char in name) or
            _name_key(name.split(".", 1)[0]) in devices):
        raise BatchSafetyError("Output name is not portable across filesystems: {!r}".format(name))


def _check_destination(path):
    """Check the entire existing path, including case aliases and linked parents.

    The caller resolves the chosen root before appending source-relative paths.
    Symlinks encountered below that root must not redirect generated files.
    This check is repeated immediately before the exclusive file create.
    """
    current = Path(path.anchor)
    for index, part in enumerate(path.parts[1:], start=1):
        if not current.exists():
            return
        if not current.is_dir():
            raise BatchSafetyError("Output parent is not a directory: {}".format(current))
        matches = [entry for entry in current.iterdir() if _name_key(entry.name) == _name_key(part)]
        if not matches:
            return
        if len(matches) != 1 or matches[0].name != part:
            raise BatchSafetyError("Output path has a case/Unicode alias: {}".format(current / part))
        current = matches[0]
        if _is_link(current):
            raise BatchSafetyError("Output path contains a symbolic link: {}".format(current))
        if index == len(path.parts) - 1:
            raise BatchSafetyError("Output already exists; overwriting is disabled: {}".format(current))


@dataclass
class ProcessOptions:
    """Options for general batch image processing."""
    width: Optional[int] = None
    height: Optional[int] = None
    scale: Optional[float] = None
    keep_aspect: bool = True
    rotate_angle: float = 0
    watermark_text: Optional[str] = None
    watermark_pos: str = "bottom-right"
    watermark_opacity: float = 0.5
    output_format: Optional[str] = None
    quality: int = 90


class BatchProcessor:
    """Legacy general-purpose batch processor (sequential, no overwrite)."""

    FORMATS = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "webp": "WEBP",
               "bmp": "BMP", "tif": "TIFF", "tiff": "TIFF"}
    SUPPORTED_EXTENSIONS = {"." + name for name in FORMATS}

    def __init__(self, options: ProcessOptions, workers: int = 4):
        self.options = options
        self.workers = workers

    def _format(self, source):
        requested = self.options.output_format
        if requested is None:
            requested = source.suffix[1:]
        if not isinstance(requested, str) or requested.lower() not in self.FORMATS:
            raise BatchSafetyError("Unsupported output format: {!r}".format(requested))
        extension = requested.lower()
        return extension, self.FORMATS[extension]

    def process_file(self, input_path: Path, output_path: Path) -> bool:
        """Write one new file, or return False without replacing an existing file.

        Encoding completes in memory before output creation. An exclusive create
        prevents an output that appears after validation from being overwritten.
        The explicitly supplied parent directory is resolved as the output root.
        """
        return self._process_file(input_path, output_path, resolve_parent=True)

    def _process_file(self, input_path, output_path, *, resolve_parent):
        created_identity = None
        output = None
        try:
            source, destination = Path(input_path), Path(output_path)
            if _is_link(source) or not source.is_file():
                raise BatchSafetyError("Input must be a regular, non-symlink image file.")
            if _is_link(destination):
                raise BatchSafetyError("Output must not be a symbolic link.")
            source = source.resolve()
            # Direct callers choose the parent as their root. Batch callers have
            # already resolved the root: do not erase newly introduced child links.
            output = (destination.parent.resolve() / destination.name
                      if resolve_parent else destination)
            _portable_name(output.name)
            if _path_key(source) == _path_key(output):
                raise BatchSafetyError("Input and output refer to the same path.")
            _check_destination(output)
            extension, save_format = self._format(source)
            with Image.open(source) as img:
                if self.options.scale is not None or self.options.width is not None or self.options.height is not None:
                    img = resize_image(img, target_width=self.options.width,
                                       target_height=self.options.height, scale=self.options.scale,
                                       keep_aspect=self.options.keep_aspect)
                if self.options.rotate_angle != 0:
                    img = rotate_image(img, self.options.rotate_angle)
                if self.options.watermark_text:
                    img = apply_text_watermark(img, text=self.options.watermark_text,
                                               position=self.options.watermark_pos,
                                               opacity=self.options.watermark_opacity)
                if self.options.output_format is not None:
                    img, _ = convert_image_format(img, output_format=extension,
                                                  quality=self.options.quality)
                save_kwargs = {"quality": self.options.quality} if save_format in ("JPEG", "WEBP") else {}
                with io.BytesIO() as buffer:
                    img.save(buffer, format=save_format, **save_kwargs)
                    payload = buffer.getvalue()
            _check_destination(output)
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("xb") as handle:
                try:
                    identity = os.fstat(handle.fileno())
                    created_identity = (identity.st_dev, identity.st_ino)
                    handle.write(payload)
                except BaseException:
                    # A one-off interrupt may arrive just after the exclusive
                    # open. Acquire identity while the owned handle is still open
                    # so cleanup can distinguish our file from a replacement.
                    if created_identity is None:
                        try:
                            identity = os.fstat(handle.fileno())
                            created_identity = (identity.st_dev, identity.st_ino)
                        except BaseException:
                            pass  # Ownership unknown: leave it, never delete by guess.
                    raise
            return True
        except BaseException as exc:
            if created_identity is not None and output is not None:
                try:
                    identity = output.lstat()
                    if not _is_link(output) and (identity.st_dev, identity.st_ino) == created_identity:
                        output.unlink()
                except FileNotFoundError:
                    pass
                except OSError as cleanup_error:
                    print("Could not remove incomplete output {}: {}".format(output, cleanup_error))
            if not isinstance(exc, Exception):
                raise
            print("Error processing {}: {}".format(input_path, exc))
            return False

    def _plan_directory(self, input_dir, output_dir, recursive):
        source_arg, destination_arg = Path(input_dir), Path(output_dir)
        if _is_link(source_arg) or _is_link(destination_arg):
            raise BatchSafetyError("Input/output directories must not be symbolic links.")
        source, destination = source_arg.resolve(), destination_arg.resolve()
        if not source.is_dir():
            raise BatchSafetyError("Input must be an existing directory.")
        if _overlap(source, destination):
            raise BatchSafetyError("Input and output must be separate, non-overlapping directories.")
        if destination.exists() and not destination.is_dir():
            raise BatchSafetyError("Output must be a directory.")
        images = []
        for root, directories, filenames in os.walk(source, followlinks=False, onerror=_walk_error):
            directories.sort()
            if recursive:
                for name in directories:
                    if _is_link(Path(root) / name):
                        raise BatchSafetyError("Recursive input contains a symbolic-link directory.")
            for name in sorted(filenames):
                file = Path(root) / name
                if file.suffix.lower() in self.SUPPORTED_EXTENSIONS:
                    if _is_link(file) or not file.is_file():
                        raise BatchSafetyError("Input image must be a regular, non-symlink file: {}".format(file))
                    images.append(file)
            if not recursive:
                break
        if not images:
            raise BatchSafetyError("No supported image files found in the input directory.")
        plan, namespace = [], {}
        for file in images:
            extension, _ = self._format(file)
            relative = file.relative_to(source)
            if self.options.output_format is not None:
                relative = relative.with_suffix("." + extension)
            for index, part in enumerate(relative.parts, start=1):
                _portable_name(part)
                prefix = relative.parts[:index]
                key = tuple(_name_key(p) for p in prefix)
                kind = "file" if index == len(relative.parts) else "directory"
                previous = namespace.get(key)
                if previous is not None and (kind == "file" or previous != (prefix, kind)):
                    raise BatchSafetyError("Batch output collision at {} (case/Unicode aliases included).".format(relative))
                namespace[key] = (prefix, kind)
            target = destination / relative
            _check_destination(target)
            plan.append((file, target))
        return plan

    def process_directory(self, input_dir: str, output_dir: str, recursive: bool = False) -> dict:
        """Preflight the entire batch before writes; raise BatchSafetyError on hazards.

        Runtime decoding/encoding failures are counted and return a partial-success
        result. Successful earlier files are kept; this is not a batch transaction.
        """
        plan = self._plan_directory(input_dir, output_dir, recursive)
        results = {"total": len(plan), "success": 0, "failed": 0}
        for source, destination in plan:
            if self._process_file(source, destination, resolve_parent=False):
                results["success"] += 1
            else:
                results["failed"] += 1
        return results
