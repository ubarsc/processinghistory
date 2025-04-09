"""
Routine tests of processing history
"""
import os
import unittest

import numpy
from osgeo import gdal, gdal_array

from processinghistory import history


gdal.UseExceptions()


def makeRaster(filename, drvr='KEA', returnDS=False):
    """
    Create a small raster file to use for tests.
    """
    nrows = ncols = 100
    imgArr = numpy.zeros((nrows, ncols), numpy.uint8)
    drvr = gdal.GetDriverByName(drvr)
    (nrows, ncols) = imgArr.shape
    gdalType = gdal_array.NumericTypeCodeToGDALTypeCode(imgArr.dtype)

    ds = drvr.Create(filename, ncols, nrows, 1, gdalType)
    band = ds.GetRasterBand(1)
    band.WriteArray(imgArr)
    if not returnDS:
        del band
        del ds
    else:
        return ds


driverList = [('KEA', 'kea'), ('HFA', 'img'), ('GTiff', 'tif')]
CHECK_AUTO_FIELDS = ['timestamp', 'login', 'cwd', 'script', 'script_dir',
    'commandline', 'python_version', 'package_version_dict']


class Fulltest(unittest.TestCase):
    """
    Run a basic test of processing history
    """
    def test_singleFile(self):
        """
        Test writing and reading history on a single file, for multiple drivers
        """
        tmpfileList = []
        userDict = {'DESCRIPTION': "A test file", 'FIELD1': "Field value"}

        for (drvrName, suffix) in driverList:
            filename = f'tst.{suffix}'
            makeRaster(filename, drvr=drvrName)
            tmpfileList.append(filename)

            # Write history to this file
            history.writeHistoryToFile(userDict, filename=filename)
            # Now read it back
            procHist = history.readHistoryFromFile(filename=filename)
            metadict = procHist[history.METADATA_BY_KEY][history.CURRENTFILE_KEY]

            # Now check it contains all of userDict
            for k in userDict:
                self.assertIn(k, metadict,
                    msg=f"User dict key {k} lost (driver={drvrName})")
                self.assertEqual(metadict[k], userDict[k],
                    msg=f"Value for user key {k} incorrect (driver={drvrName})")

            # Check it contains at least the basic automatic entries
            for k in CHECK_AUTO_FIELDS:
                self.assertIn(k, metadict,
                    msg=f"Automatic key {k} missing (driver={drvrName})")

        self.deleteTempFiles(tmpfileList)

    def test_ancestry(self):
        """
        Test a full ancestry tree with multiple ancestors
        """
        filelist = ['tst0.kea', 'tst1.kea', 'tst2.kea', 'tst3.kea']
        numFiles = len(filelist)
        for filename in filelist:
            makeRaster(filename)

        userDict = {'DESCRIPTION': "A test file", 'FIELD1': "Field value",
            'INDEX': -1}

        # Add history to each file. Zero is parent to 1 & 2, which are both
        # parents to 3.
        userDict['INDEX'] = 0
        history.writeHistoryToFile(userDict, filename=filelist[0])
        userDict['INDEX'] = 1
        history.writeHistoryToFile(userDict, parents=[filelist[0]],
            filename=filelist[1])
        userDict['INDEX'] = 2
        history.writeHistoryToFile(userDict, parents=[filelist[0]],
            filename=filelist[2])
        userDict['INDEX'] = 3
        history.writeHistoryToFile(userDict, parents=filelist[1:3],
            filename=filelist[3])

        # Read the history from the last child, and check it has everything
        procHist = history.readHistoryFromFile(filename=filelist[3])

        metadataByKey = procHist[history.METADATA_BY_KEY]
        parentsByKey = procHist[history.PARENTS_BY_KEY]
        # Do some checks
        self.assertEqual(len(metadataByKey), numFiles,
            msg="Incorrect count of metadataByKey")
        self.assertEqual(len(parentsByKey), numFiles,
            msg="Incorrect count of parentsByKey")
        self.assertEqual(len(parentsByKey[history.CURRENTFILE_KEY]), 2,
            msg="Incorrect number of parents")

        self.deleteTempFiles(filelist)
        

    def test_useDataset(self):
        """
        Test writing and reading history using an open gdal Dataset
        object instead of a filename.
        """
        filename = 'tst1.kea'
        userDict = {'DESCRIPTION': "A test file", 'FIELD1': "Field value"}

        ds = makeRaster(filename, returnDS=True)
        history.writeHistoryToFile(userDict, gdalDS=ds)
        del ds

        ds = gdal.Open(filename)
        procHist = history.readHistoryFromFile(gdalDS=ds)
        drvrName = ds.GetDriver().ShortName
        del ds

        metadict = procHist[history.METADATA_BY_KEY][history.CURRENTFILE_KEY]

        # Now check it contains all of userDict
        for k in userDict:
            self.assertIn(k, metadict,
                msg=f"User dict key {k} lost (driver={drvrName})")
            self.assertEqual(metadict[k], userDict[k],
                msg=f"Value for user key {k} incorrect (driver={drvrName})")

        self.deleteTempFiles([filename])

    @staticmethod
    def deleteTempFiles(filelist):
        """
        Delete all files in the filelist
        """
        for filename in filelist:
            if os.path.exists(filename):
                drvr = gdal.IdentifyDriver(filename)
                drvr.Delete(filename)


def mainCmd():
    unittest.main(module='processinghistory.tests', exit=False)


if __name__ == "__main__":
    mainCmd()
