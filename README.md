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

## Viewer
A simple viewer called ``historyview`` is provided, to display the processing history to the console. Since the whole lineage can be quite large and complex, no attempt is made to display the whole thing at once. Rather, the metadata dictionary or the list of parents can be displayed, for either the main file itself, or for a nominated ancestor file within the lineage.

Command line help can be displayed with ``--help``. Example output is shown below
```
$ historyview tstHist2.kea
timestamp: 2025-04-10 08:59:08+1000
login: neil
uname_os: Linux
uname_host: neil-Aspire-A315-34
uname_release: 6.11.0-21-generic
uname_version: #21~24.04.1-Ubuntu SMP PREEMPT_DYNAMIC Mon Feb 24 16:52:15
               UTC 2
uname_machine: x86_64
cwd: /home/neil/tmp
python_version: 3.11.10
package_version_dict: {"_distutils_hack": "Unknown", "processinghistory":
                      "1.0.0", "osgeo": "3.10.0"}
UNITS: Feet
DESCRIPTION: Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed
             do eiusmod tempor incididunt ut labore et dolore magna
             aliqua. Ut enim ad minim veniam, quis nostrud exercitation
             ullamco laboris nisi ut aliquip ex ea commodo consequat.
             Duis aute irure dolor in reprehenderit in voluptate velit
             esse cillum dolore eu fugiat nulla pariatur. Excepteur sint
             occaecat cupidatat non proident, sunt in culpa qui officia
             deserunt mollit anim id est laborum.
```
