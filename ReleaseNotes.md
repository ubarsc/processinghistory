# Release Notes

## Version 1.0.4
  * Explicit support for history in VRT files
  * Removed code for GTiff metadata size limits, as it appears this is no
    longer necessary
  * When gathering package version numbers, if `__version__` is unavailable, 
    fall back to using `importlib.metadata`

## Version 1.0.3
  * Cope when a parent file has no processing history

## Version 1.0.2
 * Add HISTORY_ENVVARS_TO_AUTOINCLUDE for configuring default automatic
   metadata entries

## Version 1.0.1
 * Ensure cmdline/ subdirectory is included in distribution

## Version 1.0.0
Initial release
