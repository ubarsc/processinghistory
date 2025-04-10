"""
Command line tool to view processing history in simple text form.
"""
import sys
import argparse
import textwrap
import shutil

from osgeo import gdal
from processinghistory import history


gdal.UseExceptions()


def getCmdargs():
    """
    Get command line arguments
    """
    defaultWidth = shutil.get_terminal_size().columns
    p = argparse.ArgumentParser(description="""
        Display simple text view of processing history from the given file.
        Default will display the metadata dictionary of the given file.
    """)
    p.add_argument("filename", help="Name of file to read processing history from")
    p.add_argument("--ancestor", default=None, type=str,
        help=("Filename (or key tuple string) of " +
            "selected ancestor to view, instead of the file itself"))
    p.add_argument("--showparents", default=False, action="store_true",
        help="Display parents instead of metadata dictionary. ")
    p.add_argument("--wholelineage", default=False, action="store_true",
        help="Display all parent relationships for whole lineage")
    p.add_argument("-w", "--width", default=defaultWidth, type=int,
        help="Width of display screen in characters (default=%(default)s)")
    cmdargs = p.parse_args()
    return cmdargs


def mainCmd():
    """
    Main
    """
    cmdargs = getCmdargs()

    procHist = history.readHistoryFromFile(filename=cmdargs.filename)
    if procHist is None:
        print("No processing history found in file", cmdargs.filename)
        sys.exit()

    if cmdargs.wholelineage:
        displayWholeLineage(procHist)
    else:
        key = history.CURRENTFILE_KEY
        if cmdargs.ancestor is not None:
            key = findAncestorKey(procHist, cmdargs.ancestor)

        if key is not None:
            if cmdargs.showparents:
                displayParents(key, procHist)
            else:
                metadict = procHist.metadataByKey[key]
                displayDict(metadict, cmdargs)


def findAncestorKey(procHist, ancestor):
    """
    Find the key for the given ancestor. Ancestor is a string, and can
    be either a filename or a string representation of a key tuple.

    If ancestor is already a key tuple string, this is eval-ed and returned
    as a tuple.

    If no key matches the filename, an exception is raised. If multiple
    keys match, they are printed to stdout and None is returned. Otherwise,
    return a single key tuple.

    """
    # ancestor may already be a key tuple string
    try:
        key = eval(ancestor)
    except Exception:
        key = None

    # If not a tuple, assume it is a filename, and search for it.
    if not isinstance(key, tuple):
        keylist = procHist.findKeyByFile(ancestor)
        if len(keylist) == 0:
            msg = "Ancestor '{}' not found".format(ancestor)
            raise HistoryviewTextError(msg)
        elif len(keylist) > 1:
            print("Multiple ancestors match. Specify full key tuple string")
            for key in keylist:
                print("    '{}'".format(key))
            key = None
        else:
            key = keylist[0]

    return key


def displayDict(d, cmdargs):
    """
    Display the given dictionary in simple text table form
    """
    keylist = list(d.keys())
    for key in keylist:
        keylen = len(key)
        indentWidth = keylen + 2
        indentStr = indentWidth * ' '
        tableRow = "{}: {}".format(key, d[key])
        tableRowWrapped = textwrap.wrap(tableRow, width=cmdargs.width,
            subsequent_indent=indentStr)
        for line in tableRowWrapped:
            print(line)


def displayParents(childKey, procHist):
    """
    Display the given list of parents in simple text form
    """
    indent = '    '
    print(childKey)
    parentsList = procHist.parentsByKey[childKey]
    if len(parentsList) > 0:
        for key in parentsList:
            print(indent, key)
    else:
        print(indent, "No parents")


def displayWholeLineage(procHist):
    """
    Display parent relationships for whole lineage
    """
    displayParents(history.CURRENTFILE_KEY, procHist)
    for key in procHist.parentsByKey:
        if key != history.CURRENTFILE_KEY:
            displayParents(key, procHist)


class HistoryviewTextError(Exception):
    pass
