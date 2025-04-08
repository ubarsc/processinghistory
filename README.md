# processinghistory
Store processing history on a GDAL raster file. Called programmatically from a Python script.

This package attaches small text metadata to a GDAL raster file, using GDAL's arbitrary metadata API. The metadata is in the form of a dictionary of entries for things like the script which created it, a short description of what it is, and so on. In addition to that dictionary, there is also
a copy of the history metadata for all the parent GDAL files that were inputs to creating the current file, so that the entire lineage is saved with the current file. This means the detail of its creation can be traced, even without access to the parent files.

Additional entries can be included by giving a userDict of metadata entries applicable to the file.

The metadata is stored as a JSON string in a single GDAL Metadata Item. Any entries specified in the userDict must be able to survive conversion to and from JSON.

## Usage
The following example shows adding history to a DEM image, and then to a slope and aspect image file calculated from the DEM.

```python
from processinghistory import history

demFile = "dem.tif"
slopeAspectFile = "slope_aspect.tif"

# Do some calculation to create the slope and aspect from the DEM, output
# to slopeAspectFile

# Now add processing history (pretending that demFile does not already have it).

# The DEM file is raw input data, so has no parents
userDict = {}
userDict['DESCRIPTION'] = "Elevation above sea level"
userDict['UNITS'] = "Metres"
history.writeHistoryToFile(userDict, filename=demFile)

# The slope and aspect image was calculated by this script, with demFile as a parent
userDict = {}
userDict['DESCRIPTION'] = "Slope and aspect"
parents = [demFile]
history.writeHistoryToFile(userDict, parents, filename=slopeAspectFile)
```

## Automatic Fields
The userDict given is merged with an internal dictionary of automatically generated entries. These include the following:
```
timestamp, login, cwd, script, script_dir, commandline, python_version
```
and several entries giving the various fields of the os.uname() return value.

There is also an entry called `package_version_dict`, which contains a dictionary of version numbers for as many imported Python packages as it can find. So, for example, this will include the version number of numpy and osgeo (i.e. GDAL) which are imported at the time of execution.
