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
import drizzlepac.adrizzle as adrizzle

def centroid_compare(centroid):
    return centroid[1]

class TestDriz(object):

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
            diff = [0.0, 0.0, 0.0]
            fd.write("No matches!!\n")

        elif len(distances) == 1:
            diff = [distances[0][0], distances[0][0], distances[0][0]]

            fd.write("1 match\n")
            fd.write("distance = %f flux difference = %f\n" % (distances[0][0], distances[0][1]))
            
            for j in range(2, 4):
                ylo = int(distances[0][j][0]) - 1
                yhi = int(distances[0][j][0]) + 2
                xlo = int(distances[0][j][1]) - 1
                xhi = int(distances[0][j][1]) + 2
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
                    ylo = int(distances[i][j][0]) - 1
                    yhi = int(distances[i][j][0]) + 2
                    xlo = int(distances[i][j][1]) - 1
                    xhi = int(distances[i][j][1]) + 2
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
        output_image = np.zeros(input_image.shape, dtype=input_image.dtype)
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

    def print_wcs(self, title, wcs):
        """
        Print the wcs header cards
        """
        print "=== %s ===" % title
        print wcs.to_header_string()
        
        
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

    def test_square_with_point(self):
        """
        Test do_driz square kernel with point
        """
        input = os.path.join(DATA_DIR, 'j8bt06nyq_flt.fits')
        output = os.path.join(DATA_DIR, 'output_square_point.fits')
        output_difference = os.path.join(DATA_DIR, 'difference_square_point.txt')
        output_template = os.path.join(DATA_DIR, 'reference_square_point.fits')
        
        insci = self.read_image(input)
        input_wcs = self.read_wcs(input)
        insci = self.make_point_image(insci, (500, 200), 100.0)
        inwht = np.ones(insci.shape,dtype=insci.dtype)
        output_wcs = self.read_wcs(output_template)

        naxis1 = output_wcs._naxis1
        naxis2 = output_wcs._naxis2
        outsci = np.zeros((naxis2, naxis1), dtype='float32')
        outwht = np.zeros((naxis2, naxis1), dtype='float32')
        outcon = np.zeros((1, naxis2, naxis1), dtype='i4')

        expin = 1.0
        wt_scl = expin
        in_units = 'cps'
        wcslin = distortion.utils.output_wcs([input_wcs],undistort=False)

        adrizzle.do_driz(insci, input_wcs, inwht,
                         output_wcs, outsci, outwht, outcon,
                         expin, in_units, wt_scl, wcslin_pscale=wcslin.pscale)

        output_bounds = self.bound_image(outsci)
        if self.ok:
            self.write_image(output_template, output_wcs, outsci, outwht, outcon[0])
        else:
            self.write_image(output, output_wcs, outsci, outwht, outcon[0])

            template_data = self.read_image(output_template)
            template_bounds = self.bound_image(template_data)
    
            #npt.assert_array_equal(output_bounds, template_bounds)
            
            (min_diff, med_diff, max_diff) = self.centroid_statistics("square with point", output_difference,
                                                                      outsci, template_data, 20.0, 8)

            assert(med_diff < 1.0e-6)
            assert(max_diff < 1.0e-5)

    def test_square_with_grid(self):
        """
        Test do_driz square kernel with grid
        """
        input = os.path.join(DATA_DIR, 'j8bt06nyq_flt.fits')
        output = os.path.join(DATA_DIR, 'output_square_grid.fits')
        output_difference = os.path.join(DATA_DIR, 'difference_square_grid.txt')
        output_template = os.path.join(DATA_DIR, 'reference_square_grid.fits')
        
        insci = self.read_image(input)
        input_wcs = self.read_wcs(input)
        insci = self.make_grid_image(insci, 64, 100.0)
        inwht = np.ones(insci.shape,dtype=insci.dtype)
        output_wcs = self.read_wcs(output_template)

        naxis1 = output_wcs._naxis1
        naxis2 = output_wcs._naxis2
        outsci = np.zeros((naxis2, naxis1), dtype='float32')
        outwht = np.zeros((naxis2, naxis1), dtype='float32')
        outcon = np.zeros((1, naxis2, naxis1), dtype='i4')

        expin = 1.0
        wt_scl = expin
        in_units = 'cps'
        wcslin = distortion.utils.output_wcs([input_wcs],undistort=False)

        adrizzle.do_driz(insci, input_wcs, inwht,
                         output_wcs, outsci, outwht, outcon,
                         expin, in_units, wt_scl, wcslin_pscale=wcslin.pscale)

        if self.ok:
            self.write_image(output_template, output_wcs, outsci, outwht, outcon[0])
        else:
            self.write_image(output, output_wcs, outsci, outwht, outcon[0])

            template_data = self.read_image(output_template)
            
            (min_diff, med_diff, max_diff) = self.centroid_statistics("square with grid", output_difference,
                                                                      outsci, template_data, 20.0, 8)

            assert(med_diff < 1.0e-6)
            assert(max_diff < 1.0e-5)

    def test_turbo_with_grid(self):
        """
        Test do_driz turbo kernel with grid
        """
        input = os.path.join(DATA_DIR, 'j8bt06nyq_flt.fits')
        output = os.path.join(DATA_DIR, 'output_turbo_grid.fits')
        output_difference = os.path.join(DATA_DIR, 'difference_turbo_grid.txt')
        output_template = os.path.join(DATA_DIR, 'reference_turbo_grid.fits')
        
        insci = self.read_image(input)
        input_wcs = self.read_wcs(input)
        insci = self.make_grid_image(insci, 64, 100.0)
        inwht = np.ones(insci.shape,dtype=insci.dtype)
        output_wcs = self.read_wcs(output_template)

        naxis1 = output_wcs._naxis1
        naxis2 = output_wcs._naxis2
        outsci = np.zeros((naxis2, naxis1), dtype='float32')
        outwht = np.zeros((naxis2, naxis1), dtype='float32')
        outcon = np.zeros((1, naxis2, naxis1), dtype='i4')

        expin = 1.0
        wt_scl = expin
        in_units = 'cps'
        wcslin = distortion.utils.output_wcs([input_wcs],undistort=False)

        adrizzle.do_driz(insci, input_wcs, inwht,
                         output_wcs, outsci, outwht, outcon,
                         expin, in_units, wt_scl,
                         kernel='turbo', wcslin_pscale=wcslin.pscale)

        if self.ok:
            self.write_image(output_template, output_wcs, outsci, outwht, outcon[0])
        else:
            self.write_image(output, output_wcs, outsci, outwht, outcon[0])

            template_data = self.read_image(output_template)
            
            (min_diff, med_diff, max_diff) = self.centroid_statistics("turbo with grid", output_difference,
                                                                      outsci, template_data, 20.0, 8)

            assert(med_diff < 1.0e-6)
            assert(max_diff < 1.0e-5)

    def test_gaussian_with_grid(self):
        """
        Test do_driz gaussian kernel with grid
        """
        input = os.path.join(DATA_DIR, 'j8bt06nyq_flt.fits')
        output = os.path.join(DATA_DIR, 'output_gaussian_grid.fits')
        output_difference = os.path.join(DATA_DIR, 'difference_gaussian_grid.txt')
        output_template = os.path.join(DATA_DIR, 'reference_gaussian_grid.fits')
        
        insci = self.read_image(input)
        input_wcs = self.read_wcs(input)
        insci = self.make_grid_image(insci, 64, 100.0)
        inwht = np.ones(insci.shape,dtype=insci.dtype)
        output_wcs = self.read_wcs(output_template)

        naxis1 = output_wcs._naxis1
        naxis2 = output_wcs._naxis2
        outsci = np.zeros((naxis2, naxis1), dtype='float32')
        outwht = np.zeros((naxis2, naxis1), dtype='float32')
        outcon = np.zeros((1, naxis2, naxis1), dtype='i4')

        expin = 1.0
        wt_scl = expin
        in_units = 'cps'
        wcslin = distortion.utils.output_wcs([input_wcs],undistort=False)

        adrizzle.do_driz(insci, input_wcs, inwht,
                         output_wcs, outsci, outwht, outcon,
                         expin, in_units, wt_scl,
                         kernel='gaussian', wcslin_pscale=wcslin.pscale)

        if self.ok:
            self.write_image(output_template, output_wcs, outsci, outwht, outcon[0])
        else:
            self.write_image(output, output_wcs, outsci, outwht, outcon[0])

            template_data = self.read_image(output_template)
            
            (min_diff, med_diff, max_diff) = self.centroid_statistics("gaussian with grid", output_difference,
                                                                      outsci, template_data, 20.0, 8)

            assert(med_diff < 1.0e-6)
            assert(max_diff < 2.0e-5)

    def test_lanczos_with_grid(self):
        """
        Test do_driz lanczos kernel with grid
        """
        input = os.path.join(DATA_DIR, 'j8bt06nyq_flt.fits')
        output = os.path.join(DATA_DIR, 'output_lanczos_grid.fits')
        output_difference = os.path.join(DATA_DIR, 'difference_lanczos_grid.txt')
        output_template = os.path.join(DATA_DIR, 'reference_lanczos_grid.fits')
        
        insci = self.read_image(input)
        input_wcs = self.read_wcs(input)
        insci = self.make_grid_image(insci, 64, 100.0)
        inwht = np.ones(insci.shape,dtype=insci.dtype)
        output_wcs = self.read_wcs(output_template)

        naxis1 = output_wcs._naxis1
        naxis2 = output_wcs._naxis2
        outsci = np.zeros((naxis2, naxis1), dtype='float32')
        outwht = np.zeros((naxis2, naxis1), dtype='float32')
        outcon = np.zeros((1, naxis2, naxis1), dtype='i4')

        expin = 1.0
        wt_scl = expin
        in_units = 'cps'
        wcslin = distortion.utils.output_wcs([input_wcs],undistort=False)

        adrizzle.do_driz(insci, input_wcs, inwht,
                         output_wcs, outsci, outwht, outcon,
                         expin, in_units, wt_scl,
                         kernel='lanczos3', wcslin_pscale=wcslin.pscale)

        if self.ok:
            self.write_image(output_template, output_wcs, outsci, outwht, outcon[0])
        else:
            self.write_image(output, output_wcs, outsci, outwht, outcon[0])

            template_data = self.read_image(output_template)
            
            (min_diff, med_diff, max_diff) = self.centroid_statistics("lanczos with grid", output_difference,
                                                                      outsci, template_data, 20.0, 8)

            assert(med_diff < 1.0e-6)
            assert(max_diff < 1.0e-5)

    def test_tophat_with_grid(self):
        """
        Test do_driz tophat kernel with grid
        """
        input = os.path.join(DATA_DIR, 'j8bt06nyq_flt.fits')
        output = os.path.join(DATA_DIR, 'output_tophat_grid.fits')
        output_difference = os.path.join(DATA_DIR, 'difference_tophat_grid.txt')
        output_template = os.path.join(DATA_DIR, 'reference_tophat_grid.fits')
        
        insci = self.read_image(input)
        input_wcs = self.read_wcs(input)
        insci = self.make_grid_image(insci, 64, 100.0)
        inwht = np.ones(insci.shape,dtype=insci.dtype)
        output_wcs = self.read_wcs(output_template)

        naxis1 = output_wcs._naxis1
        naxis2 = output_wcs._naxis2
        outsci = np.zeros((naxis2, naxis1), dtype='float32')
        outwht = np.zeros((naxis2, naxis1), dtype='float32')
        outcon = np.zeros((1, naxis2, naxis1), dtype='i4')

        expin = 1.0
        wt_scl = expin
        in_units = 'cps'
        wcslin = distortion.utils.output_wcs([input_wcs],undistort=False)

        adrizzle.do_driz(insci, input_wcs, inwht,
                         output_wcs, outsci, outwht, outcon,
                         expin, in_units, wt_scl,
                         kernel='tophat', wcslin_pscale=wcslin.pscale)

        if self.ok:
            self.write_image(output_template, output_wcs, outsci, outwht, outcon[0])
        else:
            self.write_image(output, output_wcs, outsci, outwht, outcon[0])

            template_data = self.read_image(output_template)
            
            (min_diff, med_diff, max_diff) = self.centroid_statistics("tophat with grid", output_difference,
                                                                      outsci, template_data, 20.0, 8)

            assert(med_diff < 1.0e-6)
            assert(max_diff < 1.0e-5)

    def test_point_with_grid(self):
        """
        Test do_driz point kernel with grid
        """
        input = os.path.join(DATA_DIR, 'j8bt06nyq_flt.fits')
        output = os.path.join(DATA_DIR, 'output_point_grid.fits')
        output_difference = os.path.join(DATA_DIR, 'difference_point_grid.txt')
        output_template = os.path.join(DATA_DIR, 'reference_point_grid.fits')
        
        insci = self.read_image(input)
        input_wcs = self.read_wcs(input)
        insci = self.make_grid_image(insci, 64, 100.0)
        inwht = np.ones(insci.shape,dtype=insci.dtype)
        output_wcs = self.read_wcs(output_template)

        naxis1 = output_wcs._naxis1
        naxis2 = output_wcs._naxis2
        outsci = np.zeros((naxis2, naxis1), dtype='float32')
        outwht = np.zeros((naxis2, naxis1), dtype='float32')
        outcon = np.zeros((1, naxis2, naxis1), dtype='i4')

        expin = 1.0
        wt_scl = expin
        in_units = 'cps'
        wcslin = distortion.utils.output_wcs([input_wcs],undistort=False)

        adrizzle.do_driz(insci, input_wcs, inwht,
                         output_wcs, outsci, outwht, outcon,
                         expin, in_units, wt_scl,
                         kernel='point', wcslin_pscale=wcslin.pscale)

        if self.ok:
            self.write_image(output_template, output_wcs, outsci, outwht, outcon[0])
        else:
            self.write_image(output, output_wcs, outsci, outwht, outcon[0])

            template_data = self.read_image(output_template)
            
            (min_diff, med_diff, max_diff) = self.centroid_statistics("point with grid", output_difference,
                                                                      outsci, template_data, 20.0, 8)

            assert(med_diff < 1.0e-6)
            assert(max_diff < 1.0e-5)

    def test_square_with_image(self):
        """
        Test do_driz square kernel
        """
        input = os.path.join(DATA_DIR, 'j8bt06nyq_flt.fits')
        output = os.path.join(DATA_DIR, 'output_square_image.fits')
        output_difference = os.path.join(DATA_DIR, 'difference_square_image.txt')
        output_template = os.path.join(DATA_DIR, 'reference_square_image.fits')
        
        insci = self.read_image(input)
        input_wcs = self.read_wcs(input)
        inwht = np.ones(insci.shape,dtype=insci.dtype)

        output_wcs = self.read_wcs(output_template)
        naxis1 = output_wcs._naxis1
        naxis2 = output_wcs._naxis2
        outsci = np.zeros((naxis2, naxis1), dtype='float32')
        outwht = np.zeros((naxis2, naxis1), dtype='float32')
        outcon = np.zeros((1, naxis2, naxis1), dtype='i4')

        expin = 1.0
        wt_scl = expin
        in_units = 'cps'
        wcslin = distortion.utils.output_wcs([input_wcs],undistort=False)

        adrizzle.do_driz(insci, input_wcs, inwht,
                         output_wcs, outsci, outwht, outcon,
                         expin, in_units, wt_scl, wcslin_pscale=wcslin.pscale)

        if self.ok:
            self.write_image(output_template, output_wcs, outsci, outwht, outcon[0])
        else:
            self.write_image(output, output_wcs, outsci, outwht, outcon[0])

            template_data = self.read_image(output_template)
            
            #assert(med_diff < 1.0e-6)
            #assert(max_diff < 1.0e-5)

    def test_turbo_with_image(self):
        """
        Test do_driz turbo kernel
        """
        input = os.path.join(DATA_DIR, 'j8bt06nyq_flt.fits')
        output = os.path.join(DATA_DIR, 'output_turbo_image.fits')
        output_difference = os.path.join(DATA_DIR, 'difference_turbo_image.txt')
        output_template = os.path.join(DATA_DIR, 'reference_turbo_image.fits')
        
        insci = self.read_image(input)
        input_wcs = self.read_wcs(input)
        inwht = np.ones(insci.shape,dtype=insci.dtype)

        output_wcs = self.read_wcs(output_template)
        naxis1 = output_wcs._naxis1
        naxis2 = output_wcs._naxis2
        outsci = np.zeros((naxis2, naxis1), dtype='float32')
        outwht = np.zeros((naxis2, naxis1), dtype='float32')
        outcon = np.zeros((1, naxis2, naxis1), dtype='i4')

        expin = 1.0
        wt_scl = expin
        in_units = 'cps'
        wcslin = distortion.utils.output_wcs([input_wcs],undistort=False)

        adrizzle.do_driz(insci, input_wcs, inwht, output_wcs, outsci, 
                         outwht, outcon, expin, in_units, wt_scl, 
                         kernel='turbo', wcslin_pscale=wcslin.pscale)

        if self.ok:
            self.write_image(output_template, output_wcs, outsci, outwht, outcon[0])
        else:
            self.write_image(output, output_wcs, outsci, outwht, outcon[0])

            template_data = self.read_image(output_template)
            
            #assert(med_diff < 1.0e-6)
            #assert(max_diff < 1.0e-5)

if __name__ == "__main__":
    go = TestDriz()
    go.test_square_with_point()
    go.test_square_with_grid()
    go.test_turbo_with_grid()
    go.test_gaussian_with_grid()
    go.test_lanczos_with_grid()
    go.test_tophat_with_grid()
    go.test_point_with_grid()
    ##go.test_square_with_image()
    ##go.test_turbo_with_image()

