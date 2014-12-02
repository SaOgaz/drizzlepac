#!/usr/bin/env python

import sys
import glob
import math
import os.path
import numpy as np
import numpy.ma as ma
import numpy.testing as npt
from astropy.io import fits
import stwcs
from stwcs import distortion
from stsci.tools import fileutil

TEST_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(TEST_DIR, 'data')
PROJECT_DIR = os.path.abspath(os.path.join(TEST_DIR, ".."))

sys.path.append(TEST_DIR)
sys.path.append(PROJECT_DIR)

import drizzlepac
import drizzlepac.ablot as ablot

def centroid_compare(centroid):
    return centroid[1]

class TestBlot(object):

    def __init__(self):
        """
        Initialize test environment
        """
        args = {}
        for flag in sys.argv[1:]:
            args[flag] = 1
        
        flags = ['ok']
        for flag in flags:
            self.__dict__[flag] = args.has_key(flag)

        self.setup()

    def setup(self):
        """
        Create python arrays used in testing
        """

    def bound_image(self, image):
        """
        Compute region where image is non-zero
        """
        coords = np.nonzero(image)
        ymin = coords[0].min()
        ymax = coords[0].max()
        xmin = coords[1].min()
        xmax = coords[1].max()
        return (ymin, ymax, xmin, xmax)
        
    def centroid(self, image, size, center):
        """
        Compute the centroid of a rectangular area
        """
        ylo = int(center[0]) - size / 2
        yhi = min(ylo + size, image.shape[0])
        xlo = int(center[1]) - size / 2
        xhi = min(xlo + size, image.shape[1])
        
        center = [0.0, 0.0, 0.0]
        for y in range(ylo, yhi):
            for x in range(xlo, xhi):
                center[0] += y * image[y,x]
                center[1] += x * image[y,x]
                center[2] += image[y,x]

        if center[2] == 0.0: return None
    
        center[0] /= center[2]
        center[1] /= center[2]
        return center        

    def centroid_close(self, list_of_centroids, size, point):
        """
        Find if any centroid is close to a point
        """
        for i in range(len(list_of_centroids)-1, -1, -1):
            if (abs(list_of_centroids[i][0] - point[0]) < size / 2 and
                abs(list_of_centroids[i][1] - point[1]) < size / 2):
                return 1

        return 0

    def centroid_distances(self, image1, image2, amp, size):
        """
        Compute a list of centroids and the distances between them in two images
        """
        distances = []
        list_of_centroids = self.centroid_list(image2, amp, size)
        for center2 in list_of_centroids:
            center1 = self.centroid(image1, size, center2)
            if center1 is None: continue

            disty = center2[0] - center1[0]
            distx = center2[1] - center1[1] 
            dist = math.sqrt(disty * disty + distx * distx)
            dflux = abs(center2[2] - center1[2])
            distances.append([dist, dflux, center1, center2])

        distances.sort(key=centroid_compare)
        return distances
        
    def centroid_list(self, image, amp, size):
        """
        Find the next centroid
        """
        list_of_centroids = []
        points = np.transpose(np.nonzero(image > amp))
        for point in points:
            if not self.centroid_close(list_of_centroids, size, point):
                center = self.centroid(image, size, point)
                list_of_centroids.append(center)
                    
        return list_of_centroids

    def centroid_statistics(self, title, fname, image1, image2, amp, size):
        """
        write centroid statistics to compare differences btw two images
        """
        stats = ("minimum", "median", "maximum")
        images = (None, None, image1, image2)
        im_type = ("", "", "test", "reference")
        
        diff = []
        distances = self.centroid_distances(image1, image2, amp, size)
        indexes = (0, len(distances)/2, len(distances)-1)
        fd = open(fname, 'w')
        fd.write("*** %s ***\n" % title)
        
        if len(distances) == 0:
            fd.write("No matches!!\n")

        elif len(distances) == 1:
            diff = [distances[0][0], distances[0][0], distances[0][0]]

            fd.write("1 match\n")
            fd.write("distance = %f flux difference = %f\n" % (distances[0][0], distances[0][1]))
            
            for j in range(2, 4):
                ylo = int(distances[0][j][0]) - 2
                yhi = int(distances[0][j][0]) + 3
                xlo = int(distances[0][j][1]) - 2
                xhi = int(distances[0][j][1]) + 3
                subimage = images[j][ylo:yhi,xlo:xhi]
                fd.write("\n%s image centroid = (%f,%f) image flux = %f\n" %
                         (im_type[j], distances[0][j][0], distances[0][j][1], distances[0][j][2]))
                fd.write(str(subimage) + "\n")
                  
        else:
            fd.write("%d matches\n" % len(distances))

            for k in range(0,3):
                i = indexes[k]
                diff.append(distances[i][0])
                fd.write("\n%s distance = %f flux difference = %f\n" % (stats[k], distances[i][0], distances[i][1]))

                for j in range(2, 4):
                    ylo = int(distances[i][j][0]) - 2
                    yhi = int(distances[i][j][0]) + 3
                    xlo = int(distances[i][j][1]) - 2
                    xhi = int(distances[i][j][1]) + 3
                    subimage = images[j][ylo:yhi,xlo:xhi]
                    fd.write("\n%s %s image centroid = (%f,%f) image flux = %f\n" %
                             (stats[k], im_type[j], distances[i][j][0], distances[i][j][1], distances[i][j][2]))
                    fd.write(str(subimage) + "\n")

        fd.close()
        return tuple(diff)
    
    def make_point_image(self, input_image, point, value):
        """
        Create an image with a single point set
        """
        output_image = np.zeros_like(input_image)
        output_image[point] = value
        return output_image   

    def make_grid_image(self, input_image, spacing, value):
        """
        Create an image with points on a grid set
        """
        output_image = np.zeros(input_image.shape, dtype=input_image.dtype)
        
        shape = output_image.shape
        for y in xrange(spacing/2, shape[0], spacing):
            for x in xrange(spacing/2, shape[1], spacing):
                output_image[y,x] = value

        return output_image   

    def read_image(self, filename):
        """
        Read the image from a fits file
        """
        path = os.path.join(DATA_DIR, filename)
        hdu = fits.open(path)

        image = hdu[1].data
        hdu.close()
        return image
    
    def read_wcs(self, filename):
        """
        Read the wcs of a fits file
        """
        path = os.path.join(DATA_DIR, filename)
        hdu = fits.open(path)
    
        wcs = stwcs.wcsutil.HSTWCS(hdu, 1)
        hdu.close()
        return wcs
        
    def write_wcs(self, hdu, image_wcs):
        """
        Update header with WCS keywords
        """ 
        hdu.header['ORIENTAT'] = image_wcs.orientat
        hdu.header['CD1_1'] = image_wcs.wcs.cd[0][0]
        hdu.header['CD1_2'] = image_wcs.wcs.cd[0][1]
        hdu.header['CD2_1'] = image_wcs.wcs.cd[1][0]
        hdu.header['CD2_2'] = image_wcs.wcs.cd[1][1]
        hdu.header['CRVAL1'] = image_wcs.wcs.crval[0]
        hdu.header['CRVAL2'] = image_wcs.wcs.crval[1]
        hdu.header['CRPIX1'] = image_wcs.wcs.crpix[0]
        hdu.header['CRPIX2'] = image_wcs.wcs.crpix[1]
        hdu.header['CTYPE1'] = image_wcs.wcs.ctype[0]
        hdu.header['CTYPE2'] = image_wcs.wcs.ctype[1]
        hdu.header['VAFACTOR'] = 1.0

    def write_image(self, filename, wcs, *args):
        """
        Read the image from a fits file
        """
        extarray = ['SCI', 'WHT', 'CTX']
        
        path = os.path.join(DATA_DIR, filename)
        if os.path.exists(path):
            os.remove(path)

        pimg = fits.HDUList()
        phdu = fits.PrimaryHDU()
        phdu.header['NDRIZIM'] = 1
        phdu.header['ROOTNAME'] = filename
        pimg.append(phdu)

        for img in args:
            # Create a MEF file with the specified extname
            extn = extarray.pop(0)
            extname = fileutil.parseExtn(extn)
            
            ehdu = fits.ImageHDU(data=img)
            ehdu.header['EXTNAME'] = extname[0]
            ehdu.header['EXTVER'] = extname[1]
            self.write_wcs(ehdu, wcs)
            pimg.append(ehdu)

        pimg.writeto(path)
        del pimg


    def test_blot_with_point(self):
        """
        Test do_blot with point image
        """
        input = os.path.join(DATA_DIR, 'j8bt06nyq_flt.fits')
        output = os.path.join(DATA_DIR, 'output_blot_point.fits')
        output_difference = os.path.join(DATA_DIR, 'difference_blot_point.txt')
        output_template = os.path.join(DATA_DIR, 'reference_blot_point.fits')
        
        insci = self.read_image(input)
        input_wcs = self.read_wcs(input)
        insci = self.make_point_image(insci, (500, 200), 40.0)
        output_wcs = self.read_wcs(output_template)

        expin = 1.0
        outsci = ablot.do_blot(insci, input_wcs, output_wcs, expin, coeffs = False)
        output_bounds = self.bound_image(outsci)

        if self.ok:
            self.write_image(output_template, output_wcs, outsci)
        else:
            self.write_image(output, output_wcs, outsci)

            template_data = self.read_image(output_template)
            template_bounds = self.bound_image(template_data)
    
            (min_diff, med_diff, max_diff) = self.centroid_statistics("blot with point", output_difference,
                                                                      outsci, template_data, 20.0, 16)

            assert(med_diff < 1.0e-6)
            assert(max_diff < 1.0e-5)

    def test_blot_with_default(self):
        """
        Test do_blot with default grid image
        """
        input = os.path.join(DATA_DIR, 'j8bt06nyq_flt.fits')
        output = os.path.join(DATA_DIR, 'output_blot_default.fits')
        output_difference = os.path.join(DATA_DIR, 'difference_blot_default.txt')
        output_template = os.path.join(DATA_DIR, 'reference_blot_default.fits')
        
        insci = self.read_image(input)
        insci = self.make_grid_image(insci, 64, 100.0)
        input_wcs = self.read_wcs(input)
        output_wcs = self.read_wcs(output_template)

        expin = 1.0
        outsci = ablot.do_blot(insci, input_wcs, output_wcs, expin, coeffs = False)

        if self.ok:
            self.write_image(output_template, output_wcs, outsci)
        else:
            self.write_image(output, output_wcs, outsci)

            template_data = self.read_image(output_template)

            (min_diff, med_diff, max_diff) = self.centroid_statistics("blot with defaults", output_difference,
                                                                      outsci, template_data, 20.0, 16)

            assert(med_diff < 1.0e-6)
            assert(max_diff < 1.0e-5)

    def test_blot_with_lan3(self):
        """
        Test do_blot with lan3 grid image
        """
        input = os.path.join(DATA_DIR, 'j8bt06nyq_flt.fits')
        output = os.path.join(DATA_DIR, 'output_blot_lan3.fits')
        output_difference = os.path.join(DATA_DIR, 'difference_blot_lan3.txt')
        output_template = os.path.join(DATA_DIR, 'reference_blot_lan3.fits')
        
        insci = self.read_image(input)
        insci = self.make_grid_image(insci, 64, 100.0)
        input_wcs = self.read_wcs(input)
        output_wcs = self.read_wcs(output_template)

        expin = 1.0
        outsci = ablot.do_blot(insci, input_wcs, output_wcs, expin, interp="lan3", coeffs = False)

        if self.ok:
            self.write_image(output_template, output_wcs, outsci)
        else:
            self.write_image(output, output_wcs, outsci)

            template_data = self.read_image(output_template)

            (min_diff, med_diff, max_diff) = self.centroid_statistics("blot with lan3", output_difference,
                                                                      outsci, template_data, 20.0, 16)

            assert(med_diff < 1.0e-6)
            assert(max_diff < 1.0e-5)

    def test_blot_with_lan5(self):
        """
        Test do_blot with lan5 grid image
        """
        input = os.path.join(DATA_DIR, 'j8bt06nyq_flt.fits')
        output = os.path.join(DATA_DIR, 'output_blot_lan5.fits')
        output_difference = os.path.join(DATA_DIR, 'difference_blot_lan5.txt')
        output_template = os.path.join(DATA_DIR, 'reference_blot_lan5.fits')
        
        insci = self.read_image(input)
        insci = self.make_grid_image(insci, 64, 100.0)
        input_wcs = self.read_wcs(input)
        output_wcs = self.read_wcs(output_template)

        expin = 1.0
        outsci = ablot.do_blot(insci, input_wcs, output_wcs, expin, interp="lan5", coeffs = False)

        if self.ok:
            self.write_image(output_template, output_wcs, outsci)
        else:
            self.write_image(output, output_wcs, outsci)

            template_data = self.read_image(output_template)

            (min_diff, med_diff, max_diff) = self.centroid_statistics("blot with lan5", output_difference,
                                                                      outsci, template_data, 20.0, 16)

            assert(med_diff < 1.0e-6)
            assert(max_diff < 1.0e-5)

    def test_blot_with_image(self):
        """
        Test do_blot with full image
        """
        input = os.path.join(DATA_DIR, 'j8bt06nyq_flt.fits')
        output = os.path.join(DATA_DIR, 'output_blot_image.fits')
        output_difference = os.path.join(DATA_DIR, 'difference_bot_image.fits')
        output_template = os.path.join(DATA_DIR, 'reference_blot_image.fits')
        
        insci = self.read_image(input)
        input_wcs = self.read_wcs(input)
        output_wcs = self.read_wcs(output_template)

        expin = 1.0
        outsci = ablot.do_blot(insci, input_wcs, output_wcs, expin, coeffs = False)

        if self.ok:
            self.write_image(output_template, output_wcs, outsci)
        else:
            self.write_image(output, output_wcs, outsci)

            template_data = self.read_image(output_template)

            #assert(med_diff < 1.0e-6)
            #assert(max_diff < 1.0e-5)

if __name__ == "__main__":
    go = TestBlot()
    go.test_blot_with_point()
    go.test_blot_with_default()
    go.test_blot_with_lan3()
    go.test_blot_with_lan5()
    #go.test_blot_with_image()

