# processinghistory
Store processing history on a GDAL raster file

This package attaches small text metadata to a GDAL raster file, using
GDAL's arbitrary metadata API. The metadata is in the form of a dictionary
of entries for things like the script which created it, a short description
of what it is, and so on. In addition to that dictionary, there is also
a copy of the history metadata for all the parent GDAL files that were
inputs to creating the current file, so that the entire lineage is saved with
the current file. This means the detail of its creation can be traced, even
without access to the parent files.

The metadata is stored as a JSON string in a single GDAL Metadata Item.

## Usage
The following example shows adding history to a DEM image, and then to a slope and aspect image file calculated from the DEM.

```
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
