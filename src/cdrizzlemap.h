#ifndef CDRIZZLEMAP_H
#define CDRIZZLEMAP_H

#include "driz_portability.h"
#include "cdrizzleutil.h"

/* Line segment structure, used for computing overlap
 * The first index on line is the endpoint
 * The second index is {x, y) coordinate of the point
 * The valid flag is non-zero if it does not intersect the image
 */

struct segment {
    double  point[2][2];
    int     valid;
};

void
initialize_segment(struct segment *self,
                   integer_t x1,
                   integer_t y1,
                   integer_t x2,
                   integer_t y2
                  );

void
show_segment(struct segment *self,
             char *str
            );

void
union_of_segments(int npoint, int jdim,
                  struct segment xybounds[],
                  integer_t bounds[2]
                 );

void
map_point(PyArrayObject * pixmap,
          const double xyin[2],
          double xyout[2]
         );

void
clip_bounds(PyArrayObject *pixmap,
            int jdim,
            struct segment *xylimit,
            struct segment *xybounds
           );

void
check_line_overlap(struct driz_param_t* p, 
                   int margin,
                   integer_t jy,
                   integer_t *xbounds
                  );

void
check_image_overlap(struct driz_param_t* p, 
                    const int margin,
                    integer_t *ybounds
                   );

#endif /* CDRIZZLEMAP_H */
