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
The whole processing history is stored as an instance of ProcessingHistory.
This has two attributes, metadataByKey and parentsByKey, both of which are
dictionary. Each of these is keyed by a tuple of the file name and the
timestamp of that file. This means that references to a file in this context
are referring to that file as created at that time, so that different versions
of a file count as distinct entities. There are entries for all files in the
lineage. The current file (i.e. the file containing this lineage) is keyed
by a special key, so that the file's own name is not embedded inside itself.

The metadataByKey dictionary has an entry for each file in the lineage, the
value is that file's own metadata dictionary.

The parentsByKey dictionary has an entry for each file in the lineage, the
value being a list of keys of the parents of that file. This dictionary stores
all the ancestry relationships for the whole lineage.

"""
import sys
import os
import getpass
import json
import time
import zlib
import base64

from osgeo import gdal


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


class ProcessingHistory:
    """
    Hold whole all ancestry and metadata for a single file
    """
    def __init__(self):
        self.metadataByKey = {}
        self.parentsByKey = {}

    def toJSON(self):
        """
        Return a JSON representation of the given ProcessingHistory
        """
        d = {
            METADATA_BY_KEY: {},
            PARENTS_BY_KEY: {}
        }
        # Copy over all elements, but convert keys from tuples to string repr.
        for k in self.metadataByKey:
            kStr = repr(k)
            d[METADATA_BY_KEY][kStr] = self.metadataByKey[k]
        for k in self.parentsByKey:
            kStr = repr(k)
            d[PARENTS_BY_KEY][kStr] = self.parentsByKey[k]

        jsonStr = json.dumps(d)
        return jsonStr

    @staticmethod
    def fromJSON(jsonStr):
        """
        Return a ProcessingHistory object from the given JSON string
        """
        d = json.loads(jsonStr)

        procHist = ProcessingHistory()
        # Copy over all elements, but convert keys from string repr back to tuples
        for kStr in d[METADATA_BY_KEY]:
            k = eval(kStr)
            procHist.metadataByKey[k] = d[METADATA_BY_KEY][kStr]
        for kStr in d[PARENTS_BY_KEY]:
            k = eval(kStr)
            procHist.parentsByKey[k] = [tuple(p) for p in d[PARENTS_BY_KEY][kStr]]

        return procHist

    def findKeyByFile(self, filename):
        """
        Return a list of all full keys from self.metadataByKey which match the
        given filename. Normally this is just a single key, so the list has
        only one element, but this should be checked.

        """
        matches = []
        for key in self.metadataByKey:
            if key != CURRENTFILE_KEY:
                if filename == key[0]:
                    matches.append(key)
        return matches


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
    procHistJSON = procHist.toJSON()
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
    procHist = ProcessingHistory()
    procHist.metadataByKey[CURRENTFILE_KEY] = metaDict

    # Now add history from each parent file
    procHist.parentsByKey[CURRENTFILE_KEY] = []
    for parentfile in parents:
        parentHist = readHistoryFromFile(filename=parentfile)

        key = (os.path.basename(parentfile),
            parentHist.metadataByKey[CURRENTFILE_KEY]['timestamp'])

        # Convert parent's "currentfile" metadata and parentage to normal key entries
        procHist.metadataByKey[key] = parentHist.metadataByKey[CURRENTFILE_KEY]
        procHist.parentsByKey[key] = parentHist.parentsByKey[CURRENTFILE_KEY]

        # Remove those from parentHist
        parentHist.metadataByKey.pop(CURRENTFILE_KEY)
        parentHist.parentsByKey.pop(CURRENTFILE_KEY)

        # Copy over all the other ancestor metadata and parentage
        procHist.metadataByKey.update(parentHist.metadataByKey)
        procHist.parentsByKey.update(parentHist.parentsByKey)

        # Add this parent as parent of current file
        procHist.parentsByKey[CURRENTFILE_KEY].append(key)

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
        procHist = ProcessingHistory.fromJSON(procHistJSON)
    else:
        procHist = None

    return procHist


class ProcessingHistoryError(Exception):
    "Generic exception for ProcessingHistory"
