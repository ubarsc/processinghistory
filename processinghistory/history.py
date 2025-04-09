"""
Add processing history to a GDAL raster file

This module attaches small text metadata to a GDAL raster file, using
GDAL's arbitrary metadata API. The metadata is in the form of a dictionary
of entries for things like the script which created it, a short description
of what it is, and so on. In addition to that dictionary, there is also
a copy of the history metadata for all the parent GDAL files that were
inputs to creating the current file, so that the entire lineage is saved with
the current file. This means the detail of its creation can be traced, even
without access to the parent files.

The metadata is stored as a JSON string in a single GDAL Metadata Item.

Data Structures
---------------
The whole processing history is stored as a dictionary with two entries, each
of which is also a dictionary. Both these are keyed by a tuple of the
file name and the timestamp of that file. This means that references to a
file in this context are referring to that file as created at that time, so
that different versions of a file count as distinct entities.

"""
import sys
import os
import getpass
import json
import time
import zlib
import base64

from osgeo import gdal


gdal.UseExceptions()


METADATA_GDALITEMNAME = "ProcessingHistory"
METADATA_GDALITEMNAME_Zipped = "ProcessingHistory_Zipped"
CURRENTFILE_KEY = "CURRENTFILE"
METADATA_BY_KEY = "metadataByKey"
PARENTS_BY_KEY = "parentsByKey"

# These GDAL drivers are known to have limits on the size of metadata which
# can be stored, and so we need to keep below these, or we lose everything.
# The values are given in bytes. The GTiff limit is actually mysteriously
# complicated, but this value seems to cover it.
metadataSizeLimitsByDriver = {'GTiff': 28000}


def makeAutomaticFields():
    """
    Generate a dictionary populated with all the fields which are automatically
    set.

    """
    dictn = {}

    # Time stamp formatted as per ISO 8601 standard, including time zone offset
    dictn['timestamp'] = time.strftime("%Y-%m-%d %H:%M:%S%z", time.localtime())

    dictn['login'] = getpass.getuser()

    uname = os.uname()
    dictn['uname_os'] = uname[0]
    dictn['uname_host'] = uname[1]
    dictn['uname_release'] = uname[2]
    dictn['uname_version'] = uname[3]
    dictn['uname_machine'] = uname[4]
    dictn['cwd'] = os.getcwd()

    if sys.argv[0] != '':
        script = sys.argv[0]
        dictn['script'] = os.path.basename(script)
        dictn['script_dir'] = os.path.dirname(script)
        dictn['commandline'] = ' '.join(sys.argv[1:])

    dictn['python_version'] = "{}.{}.{}".format(*sys.version_info)

    # Find version numbers of any external imported modules (if possible)
    moduleVersionDict = {}
    modnameList = list(sys.modules.keys())
    # To eliminate modules coming from Python's own set, we exclude any whose
    # filename starts with either sys.prefix or the same as the os module.
    # When using a virtualenv, these can be different.
    osModDir = os.path.dirname(os.__file__)
    for modname in modnameList:
        modobj = sys.modules[modname]
        if hasattr(modobj, '__file__') and modobj.__file__ is not None:
            modDirname = os.path.dirname(modobj.__file__)
            partOfPython = ((modDirname.startswith(sys.prefix) and "site-packages" not in modDirname) or
                (modDirname.startswith(osModDir) and "site-packages" not in modDirname) or
                (modname.startswith('__editable__') and modname.endswith('_finder')))
            if not partOfPython:
                toplevelModname = modname.split('.')[0]
                if toplevelModname in sys.modules:
                    moduleVersionDict[toplevelModname] = "Unknown"

    if len(moduleVersionDict) > 0:
        for modname in moduleVersionDict:
            if hasattr(sys.modules[modname], '__version__'):
                moduleVersionDict[modname] = str(sys.modules[modname].__version__)
        dictn['package_version_dict'] = json.dumps(moduleVersionDict)

    return dictn


def writeHistoryToFile(userDict={}, parents=[], *, filename=None, gdalDS=None):
    """
    Make the full processing history and save to the given file.

    File can be specified as either a filename string or an open GDAL Dataset

    """
    procHist = makeProcessingHistory(userDict, parents)

    if filename is not None:
        ds = gdal.Open(filename, gdal.GA_Update)
    else:
        ds = gdalDS

    if ds is None:
        raise ProcessingHistoryError("Must supply either filename or gdalDS")

    drvrName = ds.GetDriver().ShortName

    # Convert to JSON
    procHistJSON = json.dumps(procHist)
    gdalMetadataName = METADATA_GDALITEMNAME
    gdalMetadataValue = procHistJSON

    # Some drivers (GTiff) have size limits, so compress if required.
    if drvrName in metadataSizeLimitsByDriver:
        # The driver has size limits, so check if we need to compress
        valueLen = len(gdalMetadataValue)
        sizeLimit = metadataSizeLimitsByDriver[drvrName]
        if valueLen > sizeLimit:
            procHistJSON_zipped = base64.b64encode(
                zlib.compress(gdalMetadataValue, 9))
            gdalMetadataName = METADATA_GDALITEMNAME_Zipped
            gdalMetadataValue = procHistJSON_zipped

        # Check again, and if still too large, raise an exception
        valueLen = len(gdalMetadataValue)
        if valueLen > metadataSizeLimitsByDriver[drvrName]:
            msg = ("Processing history size (compressed) = {} bytes. {} driver " +
                   "is limited to {}").format(valueLen, drvrName, sizeLimit)
            raise ProcessingHistoryError(msg)

    # Save in the Dataset
    ds.SetMetadataItem(gdalMetadataName, gdalMetadataValue)


def makeProcessingHistory(userDict, parents):
    """
    Make the full processing history. Returns a dictionary with all metadata
    and parentage relationships.
    """
    # Make the metadata dictionary for the current file
    metaDict = makeAutomaticFields()
    metaDict.update(userDict)

    # Make the whole processing history dictionary, starting with entries for
    # the current file
    metadataByKey = {CURRENTFILE_KEY: metaDict}
    parentsByKey = {CURRENTFILE_KEY: []}
    procHist = {
        METADATA_BY_KEY: metadataByKey,
        PARENTS_BY_KEY: parentsByKey
    }

    # Now add history from each parent file
    for parentfile in parents:
        parentHist = readHistoryFromFile(filename=parentfile)

        # Note that the key tuple is turned into a string, so that
        # it will be JSON-proof
        key = repr((os.path.basename(parentfile),
            parentHist[METADATA_BY_KEY][CURRENTFILE_KEY]['timestamp']))

        # Convert parent's "currentfile" metadata and parentage to normal key entries
        metadataByKey[key] = parentHist[METADATA_BY_KEY][CURRENTFILE_KEY]
        parentsByKey[key] = parentHist[PARENTS_BY_KEY][CURRENTFILE_KEY]

        # Remove those from parentHist
        parentHist[METADATA_BY_KEY].pop(CURRENTFILE_KEY)
        parentHist[PARENTS_BY_KEY].pop(CURRENTFILE_KEY)

        # Copy over all the other ancestor metadata and parentage
        metadataByKey.update(parentHist[METADATA_BY_KEY])
        parentsByKey.update(parentHist[PARENTS_BY_KEY])

        # Add this parent as parent of current file
        parentsByKey[CURRENTFILE_KEY].append(key)

    return procHist


def readHistoryFromFile(filename=None, gdalDS=None):
    """
    Read processing history from file.

    File to read can be specified as either a filename, or an open GDAL
    Dataset object.

    """
    if filename is not None:
        ds = gdal.Open(filename)
    else:
        ds = gdalDS

    procHistJSON = ds.GetMetadataItem(METADATA_GDALITEMNAME)
    if procHistJSON is None:
        procHistJSON_zipped = ds.GetMetadataItem(METADATA_GDALITEMNAME_Zipped)
        if procHistJSON_zipped is not None:
            procHistJSON = zlib.decompress(base64.b64decode(procHistJSON_zipped))

    if procHistJSON is not None:
        procHist = json.loads(procHistJSON)
    else:
        procHist = None

    return procHist


class ProcessingHistoryError(Exception):
    "Generic exception for ProcessingHistory"
