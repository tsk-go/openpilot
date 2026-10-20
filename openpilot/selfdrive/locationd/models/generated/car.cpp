#include "car.h"

namespace {
#define DIM 9
#define EDIM 9
#define MEDIM 9
typedef void (*Hfun)(double *, double *, double *);

double mass;

void set_mass(double x){ mass = x;}

double rotational_inertia;

void set_rotational_inertia(double x){ rotational_inertia = x;}

double center_to_front;

void set_center_to_front(double x){ center_to_front = x;}

double center_to_rear;

void set_center_to_rear(double x){ center_to_rear = x;}

double stiffness_front;

void set_stiffness_front(double x){ stiffness_front = x;}

double stiffness_rear;

void set_stiffness_rear(double x){ stiffness_rear = x;}
const static double MAHA_THRESH_25 = 3.8414588206941227;
const static double MAHA_THRESH_24 = 5.991464547107981;
const static double MAHA_THRESH_30 = 3.8414588206941227;
const static double MAHA_THRESH_26 = 3.8414588206941227;
const static double MAHA_THRESH_27 = 3.8414588206941227;
const static double MAHA_THRESH_29 = 3.8414588206941227;
const static double MAHA_THRESH_28 = 3.8414588206941227;
const static double MAHA_THRESH_31 = 3.8414588206941227;

/******************************************************************************
 *                      Code generated with SymPy 1.14.0                      *
 *                                                                            *
 *              See http://www.sympy.org/ for more information.               *
 *                                                                            *
 *                         This file is part of 'ekf'                         *
 ******************************************************************************/
void err_fun(double *nom_x, double *delta_x, double *out_5507159804932095856) {
   out_5507159804932095856[0] = delta_x[0] + nom_x[0];
   out_5507159804932095856[1] = delta_x[1] + nom_x[1];
   out_5507159804932095856[2] = delta_x[2] + nom_x[2];
   out_5507159804932095856[3] = delta_x[3] + nom_x[3];
   out_5507159804932095856[4] = delta_x[4] + nom_x[4];
   out_5507159804932095856[5] = delta_x[5] + nom_x[5];
   out_5507159804932095856[6] = delta_x[6] + nom_x[6];
   out_5507159804932095856[7] = delta_x[7] + nom_x[7];
   out_5507159804932095856[8] = delta_x[8] + nom_x[8];
}
void inv_err_fun(double *nom_x, double *true_x, double *out_3708402617549620907) {
   out_3708402617549620907[0] = -nom_x[0] + true_x[0];
   out_3708402617549620907[1] = -nom_x[1] + true_x[1];
   out_3708402617549620907[2] = -nom_x[2] + true_x[2];
   out_3708402617549620907[3] = -nom_x[3] + true_x[3];
   out_3708402617549620907[4] = -nom_x[4] + true_x[4];
   out_3708402617549620907[5] = -nom_x[5] + true_x[5];
   out_3708402617549620907[6] = -nom_x[6] + true_x[6];
   out_3708402617549620907[7] = -nom_x[7] + true_x[7];
   out_3708402617549620907[8] = -nom_x[8] + true_x[8];
}
void H_mod_fun(double *state, double *out_3048507717174445082) {
   out_3048507717174445082[0] = 1.0;
   out_3048507717174445082[1] = 0.0;
   out_3048507717174445082[2] = 0.0;
   out_3048507717174445082[3] = 0.0;
   out_3048507717174445082[4] = 0.0;
   out_3048507717174445082[5] = 0.0;
   out_3048507717174445082[6] = 0.0;
   out_3048507717174445082[7] = 0.0;
   out_3048507717174445082[8] = 0.0;
   out_3048507717174445082[9] = 0.0;
   out_3048507717174445082[10] = 1.0;
   out_3048507717174445082[11] = 0.0;
   out_3048507717174445082[12] = 0.0;
   out_3048507717174445082[13] = 0.0;
   out_3048507717174445082[14] = 0.0;
   out_3048507717174445082[15] = 0.0;
   out_3048507717174445082[16] = 0.0;
   out_3048507717174445082[17] = 0.0;
   out_3048507717174445082[18] = 0.0;
   out_3048507717174445082[19] = 0.0;
   out_3048507717174445082[20] = 1.0;
   out_3048507717174445082[21] = 0.0;
   out_3048507717174445082[22] = 0.0;
   out_3048507717174445082[23] = 0.0;
   out_3048507717174445082[24] = 0.0;
   out_3048507717174445082[25] = 0.0;
   out_3048507717174445082[26] = 0.0;
   out_3048507717174445082[27] = 0.0;
   out_3048507717174445082[28] = 0.0;
   out_3048507717174445082[29] = 0.0;
   out_3048507717174445082[30] = 1.0;
   out_3048507717174445082[31] = 0.0;
   out_3048507717174445082[32] = 0.0;
   out_3048507717174445082[33] = 0.0;
   out_3048507717174445082[34] = 0.0;
   out_3048507717174445082[35] = 0.0;
   out_3048507717174445082[36] = 0.0;
   out_3048507717174445082[37] = 0.0;
   out_3048507717174445082[38] = 0.0;
   out_3048507717174445082[39] = 0.0;
   out_3048507717174445082[40] = 1.0;
   out_3048507717174445082[41] = 0.0;
   out_3048507717174445082[42] = 0.0;
   out_3048507717174445082[43] = 0.0;
   out_3048507717174445082[44] = 0.0;
   out_3048507717174445082[45] = 0.0;
   out_3048507717174445082[46] = 0.0;
   out_3048507717174445082[47] = 0.0;
   out_3048507717174445082[48] = 0.0;
   out_3048507717174445082[49] = 0.0;
   out_3048507717174445082[50] = 1.0;
   out_3048507717174445082[51] = 0.0;
   out_3048507717174445082[52] = 0.0;
   out_3048507717174445082[53] = 0.0;
   out_3048507717174445082[54] = 0.0;
   out_3048507717174445082[55] = 0.0;
   out_3048507717174445082[56] = 0.0;
   out_3048507717174445082[57] = 0.0;
   out_3048507717174445082[58] = 0.0;
   out_3048507717174445082[59] = 0.0;
   out_3048507717174445082[60] = 1.0;
   out_3048507717174445082[61] = 0.0;
   out_3048507717174445082[62] = 0.0;
   out_3048507717174445082[63] = 0.0;
   out_3048507717174445082[64] = 0.0;
   out_3048507717174445082[65] = 0.0;
   out_3048507717174445082[66] = 0.0;
   out_3048507717174445082[67] = 0.0;
   out_3048507717174445082[68] = 0.0;
   out_3048507717174445082[69] = 0.0;
   out_3048507717174445082[70] = 1.0;
   out_3048507717174445082[71] = 0.0;
   out_3048507717174445082[72] = 0.0;
   out_3048507717174445082[73] = 0.0;
   out_3048507717174445082[74] = 0.0;
   out_3048507717174445082[75] = 0.0;
   out_3048507717174445082[76] = 0.0;
   out_3048507717174445082[77] = 0.0;
   out_3048507717174445082[78] = 0.0;
   out_3048507717174445082[79] = 0.0;
   out_3048507717174445082[80] = 1.0;
}
void f_fun(double *state, double dt, double *out_2392350810154680862) {
   out_2392350810154680862[0] = state[0];
   out_2392350810154680862[1] = state[1];
   out_2392350810154680862[2] = state[2];
   out_2392350810154680862[3] = state[3];
   out_2392350810154680862[4] = state[4];
   out_2392350810154680862[5] = dt*((-state[4] + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(mass*state[4]))*state[6] - 9.8100000000000005*state[8] + stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(mass*state[1]) + (-stiffness_front*state[0] - stiffness_rear*state[0])*state[5]/(mass*state[4])) + state[5];
   out_2392350810154680862[6] = dt*(center_to_front*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(rotational_inertia*state[1]) + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])*state[5]/(rotational_inertia*state[4]) + (-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])*state[6]/(rotational_inertia*state[4])) + state[6];
   out_2392350810154680862[7] = state[7];
   out_2392350810154680862[8] = state[8];
}
void F_fun(double *state, double dt, double *out_3545351747806026181) {
   out_3545351747806026181[0] = 1;
   out_3545351747806026181[1] = 0;
   out_3545351747806026181[2] = 0;
   out_3545351747806026181[3] = 0;
   out_3545351747806026181[4] = 0;
   out_3545351747806026181[5] = 0;
   out_3545351747806026181[6] = 0;
   out_3545351747806026181[7] = 0;
   out_3545351747806026181[8] = 0;
   out_3545351747806026181[9] = 0;
   out_3545351747806026181[10] = 1;
   out_3545351747806026181[11] = 0;
   out_3545351747806026181[12] = 0;
   out_3545351747806026181[13] = 0;
   out_3545351747806026181[14] = 0;
   out_3545351747806026181[15] = 0;
   out_3545351747806026181[16] = 0;
   out_3545351747806026181[17] = 0;
   out_3545351747806026181[18] = 0;
   out_3545351747806026181[19] = 0;
   out_3545351747806026181[20] = 1;
   out_3545351747806026181[21] = 0;
   out_3545351747806026181[22] = 0;
   out_3545351747806026181[23] = 0;
   out_3545351747806026181[24] = 0;
   out_3545351747806026181[25] = 0;
   out_3545351747806026181[26] = 0;
   out_3545351747806026181[27] = 0;
   out_3545351747806026181[28] = 0;
   out_3545351747806026181[29] = 0;
   out_3545351747806026181[30] = 1;
   out_3545351747806026181[31] = 0;
   out_3545351747806026181[32] = 0;
   out_3545351747806026181[33] = 0;
   out_3545351747806026181[34] = 0;
   out_3545351747806026181[35] = 0;
   out_3545351747806026181[36] = 0;
   out_3545351747806026181[37] = 0;
   out_3545351747806026181[38] = 0;
   out_3545351747806026181[39] = 0;
   out_3545351747806026181[40] = 1;
   out_3545351747806026181[41] = 0;
   out_3545351747806026181[42] = 0;
   out_3545351747806026181[43] = 0;
   out_3545351747806026181[44] = 0;
   out_3545351747806026181[45] = dt*(stiffness_front*(-state[2] - state[3] + state[7])/(mass*state[1]) + (-stiffness_front - stiffness_rear)*state[5]/(mass*state[4]) + (-center_to_front*stiffness_front + center_to_rear*stiffness_rear)*state[6]/(mass*state[4]));
   out_3545351747806026181[46] = -dt*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(mass*pow(state[1], 2));
   out_3545351747806026181[47] = -dt*stiffness_front*state[0]/(mass*state[1]);
   out_3545351747806026181[48] = -dt*stiffness_front*state[0]/(mass*state[1]);
   out_3545351747806026181[49] = dt*((-1 - (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(mass*pow(state[4], 2)))*state[6] - (-stiffness_front*state[0] - stiffness_rear*state[0])*state[5]/(mass*pow(state[4], 2)));
   out_3545351747806026181[50] = dt*(-stiffness_front*state[0] - stiffness_rear*state[0])/(mass*state[4]) + 1;
   out_3545351747806026181[51] = dt*(-state[4] + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(mass*state[4]));
   out_3545351747806026181[52] = dt*stiffness_front*state[0]/(mass*state[1]);
   out_3545351747806026181[53] = -9.8100000000000005*dt;
   out_3545351747806026181[54] = dt*(center_to_front*stiffness_front*(-state[2] - state[3] + state[7])/(rotational_inertia*state[1]) + (-center_to_front*stiffness_front + center_to_rear*stiffness_rear)*state[5]/(rotational_inertia*state[4]) + (-pow(center_to_front, 2)*stiffness_front - pow(center_to_rear, 2)*stiffness_rear)*state[6]/(rotational_inertia*state[4]));
   out_3545351747806026181[55] = -center_to_front*dt*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(rotational_inertia*pow(state[1], 2));
   out_3545351747806026181[56] = -center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_3545351747806026181[57] = -center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_3545351747806026181[58] = dt*(-(-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])*state[5]/(rotational_inertia*pow(state[4], 2)) - (-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])*state[6]/(rotational_inertia*pow(state[4], 2)));
   out_3545351747806026181[59] = dt*(-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(rotational_inertia*state[4]);
   out_3545351747806026181[60] = dt*(-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])/(rotational_inertia*state[4]) + 1;
   out_3545351747806026181[61] = center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_3545351747806026181[62] = 0;
   out_3545351747806026181[63] = 0;
   out_3545351747806026181[64] = 0;
   out_3545351747806026181[65] = 0;
   out_3545351747806026181[66] = 0;
   out_3545351747806026181[67] = 0;
   out_3545351747806026181[68] = 0;
   out_3545351747806026181[69] = 0;
   out_3545351747806026181[70] = 1;
   out_3545351747806026181[71] = 0;
   out_3545351747806026181[72] = 0;
   out_3545351747806026181[73] = 0;
   out_3545351747806026181[74] = 0;
   out_3545351747806026181[75] = 0;
   out_3545351747806026181[76] = 0;
   out_3545351747806026181[77] = 0;
   out_3545351747806026181[78] = 0;
   out_3545351747806026181[79] = 0;
   out_3545351747806026181[80] = 1;
}
void h_25(double *state, double *unused, double *out_100883961627628976) {
   out_100883961627628976[0] = state[6];
}
void H_25(double *state, double *unused, double *out_7952199542359109922) {
   out_7952199542359109922[0] = 0;
   out_7952199542359109922[1] = 0;
   out_7952199542359109922[2] = 0;
   out_7952199542359109922[3] = 0;
   out_7952199542359109922[4] = 0;
   out_7952199542359109922[5] = 0;
   out_7952199542359109922[6] = 1;
   out_7952199542359109922[7] = 0;
   out_7952199542359109922[8] = 0;
}
void h_24(double *state, double *unused, double *out_8651264488955021024) {
   out_8651264488955021024[0] = state[4];
   out_8651264488955021024[1] = state[5];
}
void H_24(double *state, double *unused, double *out_3918972724758923593) {
   out_3918972724758923593[0] = 0;
   out_3918972724758923593[1] = 0;
   out_3918972724758923593[2] = 0;
   out_3918972724758923593[3] = 0;
   out_3918972724758923593[4] = 1;
   out_3918972724758923593[5] = 0;
   out_3918972724758923593[6] = 0;
   out_3918972724758923593[7] = 0;
   out_3918972724758923593[8] = 0;
   out_3918972724758923593[9] = 0;
   out_3918972724758923593[10] = 0;
   out_3918972724758923593[11] = 0;
   out_3918972724758923593[12] = 0;
   out_3918972724758923593[13] = 0;
   out_3918972724758923593[14] = 1;
   out_3918972724758923593[15] = 0;
   out_3918972724758923593[16] = 0;
   out_3918972724758923593[17] = 0;
}
void h_30(double *state, double *unused, double *out_975203001893898031) {
   out_975203001893898031[0] = state[4];
}
void H_30(double *state, double *unused, double *out_7976211572843193067) {
   out_7976211572843193067[0] = 0;
   out_7976211572843193067[1] = 0;
   out_7976211572843193067[2] = 0;
   out_7976211572843193067[3] = 0;
   out_7976211572843193067[4] = 1;
   out_7976211572843193067[5] = 0;
   out_7976211572843193067[6] = 0;
   out_7976211572843193067[7] = 0;
   out_7976211572843193067[8] = 0;
}
void h_26(double *state, double *unused, double *out_5976876269554743676) {
   out_5976876269554743676[0] = state[7];
}
void H_26(double *state, double *unused, double *out_4210696223485053698) {
   out_4210696223485053698[0] = 0;
   out_4210696223485053698[1] = 0;
   out_4210696223485053698[2] = 0;
   out_4210696223485053698[3] = 0;
   out_4210696223485053698[4] = 0;
   out_4210696223485053698[5] = 0;
   out_4210696223485053698[6] = 0;
   out_4210696223485053698[7] = 1;
   out_4210696223485053698[8] = 0;
}
void h_27(double *state, double *unused, double *out_4900789306033216669) {
   out_4900789306033216669[0] = state[3];
}
void H_27(double *state, double *unused, double *out_5752617501659249850) {
   out_5752617501659249850[0] = 0;
   out_5752617501659249850[1] = 0;
   out_5752617501659249850[2] = 0;
   out_5752617501659249850[3] = 1;
   out_5752617501659249850[4] = 0;
   out_5752617501659249850[5] = 0;
   out_5752617501659249850[6] = 0;
   out_5752617501659249850[7] = 0;
   out_5752617501659249850[8] = 0;
}
void h_29(double *state, double *unused, double *out_1918712854795560466) {
   out_1918712854795560466[0] = state[1];
}
void H_29(double *state, double *unused, double *out_7465980228528800883) {
   out_7465980228528800883[0] = 0;
   out_7465980228528800883[1] = 1;
   out_7465980228528800883[2] = 0;
   out_7465980228528800883[3] = 0;
   out_7465980228528800883[4] = 0;
   out_7465980228528800883[5] = 0;
   out_7465980228528800883[6] = 0;
   out_7465980228528800883[7] = 0;
   out_7465980228528800883[8] = 0;
}
void h_28(double *state, double *unused, double *out_7903224896595378112) {
   out_7903224896595378112[0] = state[0];
}
void H_28(double *state, double *unused, double *out_5898364828111220159) {
   out_5898364828111220159[0] = 1;
   out_5898364828111220159[1] = 0;
   out_5898364828111220159[2] = 0;
   out_5898364828111220159[3] = 0;
   out_5898364828111220159[4] = 0;
   out_5898364828111220159[5] = 0;
   out_5898364828111220159[6] = 0;
   out_5898364828111220159[7] = 0;
   out_5898364828111220159[8] = 0;
}
void h_31(double *state, double *unused, double *out_7662381295193043465) {
   out_7662381295193043465[0] = state[8];
}
void H_31(double *state, double *unused, double *out_7982845504236070350) {
   out_7982845504236070350[0] = 0;
   out_7982845504236070350[1] = 0;
   out_7982845504236070350[2] = 0;
   out_7982845504236070350[3] = 0;
   out_7982845504236070350[4] = 0;
   out_7982845504236070350[5] = 0;
   out_7982845504236070350[6] = 0;
   out_7982845504236070350[7] = 0;
   out_7982845504236070350[8] = 1;
}
#include <eigen3/Eigen/Dense>
#include <iostream>

typedef Eigen::Matrix<double, DIM, DIM, Eigen::RowMajor> DDM;
typedef Eigen::Matrix<double, EDIM, EDIM, Eigen::RowMajor> EEM;
typedef Eigen::Matrix<double, DIM, EDIM, Eigen::RowMajor> DEM;

void predict(double *in_x, double *in_P, double *in_Q, double dt) {
  typedef Eigen::Matrix<double, MEDIM, MEDIM, Eigen::RowMajor> RRM;

  double nx[DIM] = {0};
  double in_F[EDIM*EDIM] = {0};

  // functions from sympy
  f_fun(in_x, dt, nx);
  F_fun(in_x, dt, in_F);


  EEM F(in_F);
  EEM P(in_P);
  EEM Q(in_Q);

  RRM F_main = F.topLeftCorner(MEDIM, MEDIM);
  P.topLeftCorner(MEDIM, MEDIM) = (F_main * P.topLeftCorner(MEDIM, MEDIM)) * F_main.transpose();
  P.topRightCorner(MEDIM, EDIM - MEDIM) = F_main * P.topRightCorner(MEDIM, EDIM - MEDIM);
  P.bottomLeftCorner(EDIM - MEDIM, MEDIM) = P.bottomLeftCorner(EDIM - MEDIM, MEDIM) * F_main.transpose();

  P = P + dt*Q;

  // copy out state
  memcpy(in_x, nx, DIM * sizeof(double));
  memcpy(in_P, P.data(), EDIM * EDIM * sizeof(double));
}

// note: extra_args dim only correct when null space projecting
// otherwise 1
template <int ZDIM, int EADIM, bool MAHA_TEST>
void update(double *in_x, double *in_P, Hfun h_fun, Hfun H_fun, Hfun Hea_fun, double *in_z, double *in_R, double *in_ea, double MAHA_THRESHOLD) {
  typedef Eigen::Matrix<double, ZDIM, ZDIM, Eigen::RowMajor> ZZM;
  typedef Eigen::Matrix<double, ZDIM, DIM, Eigen::RowMajor> ZDM;
  typedef Eigen::Matrix<double, Eigen::Dynamic, EDIM, Eigen::RowMajor> XEM;
  //typedef Eigen::Matrix<double, EDIM, ZDIM, Eigen::RowMajor> EZM;
  typedef Eigen::Matrix<double, Eigen::Dynamic, 1> X1M;
  typedef Eigen::Matrix<double, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor> XXM;

  double in_hx[ZDIM] = {0};
  double in_H[ZDIM * DIM] = {0};
  double in_H_mod[EDIM * DIM] = {0};
  double delta_x[EDIM] = {0};
  double x_new[DIM] = {0};


  // state x, P
  Eigen::Matrix<double, ZDIM, 1> z(in_z);
  EEM P(in_P);
  ZZM pre_R(in_R);

  // functions from sympy
  h_fun(in_x, in_ea, in_hx);
  H_fun(in_x, in_ea, in_H);
  ZDM pre_H(in_H);

  // get y (y = z - hx)
  Eigen::Matrix<double, ZDIM, 1> pre_y(in_hx); pre_y = z - pre_y;
  X1M y; XXM H; XXM R;
  if (Hea_fun){
    typedef Eigen::Matrix<double, ZDIM, EADIM, Eigen::RowMajor> ZAM;
    double in_Hea[ZDIM * EADIM] = {0};
    Hea_fun(in_x, in_ea, in_Hea);
    ZAM Hea(in_Hea);
    XXM A = Hea.transpose().fullPivLu().kernel();


    y = A.transpose() * pre_y;
    H = A.transpose() * pre_H;
    R = A.transpose() * pre_R * A;
  } else {
    y = pre_y;
    H = pre_H;
    R = pre_R;
  }
  // get modified H
  H_mod_fun(in_x, in_H_mod);
  DEM H_mod(in_H_mod);
  XEM H_err = H * H_mod;

  // Do mahalobis distance test
  if (MAHA_TEST){
    XXM a = (H_err * P * H_err.transpose() + R).inverse();
    double maha_dist = y.transpose() * a * y;
    if (maha_dist > MAHA_THRESHOLD){
      R = 1.0e16 * R;
    }
  }

  // Outlier resilient weighting
  double weight = 1;//(1.5)/(1 + y.squaredNorm()/R.sum());

  // kalman gains and I_KH
  XXM S = ((H_err * P) * H_err.transpose()) + R/weight;
  XEM KT = S.fullPivLu().solve(H_err * P.transpose());
  //EZM K = KT.transpose(); TODO: WHY DOES THIS NOT COMPILE?
  //EZM K = S.fullPivLu().solve(H_err * P.transpose()).transpose();
  //std::cout << "Here is the matrix rot:\n" << K << std::endl;
  EEM I_KH = Eigen::Matrix<double, EDIM, EDIM>::Identity() - (KT.transpose() * H_err);

  // update state by injecting dx
  Eigen::Matrix<double, EDIM, 1> dx(delta_x);
  dx  = (KT.transpose() * y);
  memcpy(delta_x, dx.data(), EDIM * sizeof(double));
  err_fun(in_x, delta_x, x_new);
  Eigen::Matrix<double, DIM, 1> x(x_new);

  // update cov
  P = ((I_KH * P) * I_KH.transpose()) + ((KT.transpose() * R) * KT);

  // copy out state
  memcpy(in_x, x.data(), DIM * sizeof(double));
  memcpy(in_P, P.data(), EDIM * EDIM * sizeof(double));
  memcpy(in_z, y.data(), y.rows() * sizeof(double));
}




}
extern "C" {

void car_update_25(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_25, H_25, NULL, in_z, in_R, in_ea, MAHA_THRESH_25);
}
void car_update_24(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<2, 3, 0>(in_x, in_P, h_24, H_24, NULL, in_z, in_R, in_ea, MAHA_THRESH_24);
}
void car_update_30(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_30, H_30, NULL, in_z, in_R, in_ea, MAHA_THRESH_30);
}
void car_update_26(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_26, H_26, NULL, in_z, in_R, in_ea, MAHA_THRESH_26);
}
void car_update_27(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_27, H_27, NULL, in_z, in_R, in_ea, MAHA_THRESH_27);
}
void car_update_29(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_29, H_29, NULL, in_z, in_R, in_ea, MAHA_THRESH_29);
}
void car_update_28(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_28, H_28, NULL, in_z, in_R, in_ea, MAHA_THRESH_28);
}
void car_update_31(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_31, H_31, NULL, in_z, in_R, in_ea, MAHA_THRESH_31);
}
void car_err_fun(double *nom_x, double *delta_x, double *out_5507159804932095856) {
  err_fun(nom_x, delta_x, out_5507159804932095856);
}
void car_inv_err_fun(double *nom_x, double *true_x, double *out_3708402617549620907) {
  inv_err_fun(nom_x, true_x, out_3708402617549620907);
}
void car_H_mod_fun(double *state, double *out_3048507717174445082) {
  H_mod_fun(state, out_3048507717174445082);
}
void car_f_fun(double *state, double dt, double *out_2392350810154680862) {
  f_fun(state,  dt, out_2392350810154680862);
}
void car_F_fun(double *state, double dt, double *out_3545351747806026181) {
  F_fun(state,  dt, out_3545351747806026181);
}
void car_h_25(double *state, double *unused, double *out_100883961627628976) {
  h_25(state, unused, out_100883961627628976);
}
void car_H_25(double *state, double *unused, double *out_7952199542359109922) {
  H_25(state, unused, out_7952199542359109922);
}
void car_h_24(double *state, double *unused, double *out_8651264488955021024) {
  h_24(state, unused, out_8651264488955021024);
}
void car_H_24(double *state, double *unused, double *out_3918972724758923593) {
  H_24(state, unused, out_3918972724758923593);
}
void car_h_30(double *state, double *unused, double *out_975203001893898031) {
  h_30(state, unused, out_975203001893898031);
}
void car_H_30(double *state, double *unused, double *out_7976211572843193067) {
  H_30(state, unused, out_7976211572843193067);
}
void car_h_26(double *state, double *unused, double *out_5976876269554743676) {
  h_26(state, unused, out_5976876269554743676);
}
void car_H_26(double *state, double *unused, double *out_4210696223485053698) {
  H_26(state, unused, out_4210696223485053698);
}
void car_h_27(double *state, double *unused, double *out_4900789306033216669) {
  h_27(state, unused, out_4900789306033216669);
}
void car_H_27(double *state, double *unused, double *out_5752617501659249850) {
  H_27(state, unused, out_5752617501659249850);
}
void car_h_29(double *state, double *unused, double *out_1918712854795560466) {
  h_29(state, unused, out_1918712854795560466);
}
void car_H_29(double *state, double *unused, double *out_7465980228528800883) {
  H_29(state, unused, out_7465980228528800883);
}
void car_h_28(double *state, double *unused, double *out_7903224896595378112) {
  h_28(state, unused, out_7903224896595378112);
}
void car_H_28(double *state, double *unused, double *out_5898364828111220159) {
  H_28(state, unused, out_5898364828111220159);
}
void car_h_31(double *state, double *unused, double *out_7662381295193043465) {
  h_31(state, unused, out_7662381295193043465);
}
void car_H_31(double *state, double *unused, double *out_7982845504236070350) {
  H_31(state, unused, out_7982845504236070350);
}
void car_predict(double *in_x, double *in_P, double *in_Q, double dt) {
  predict(in_x, in_P, in_Q, dt);
}
void car_set_mass(double x) {
  set_mass(x);
}
void car_set_rotational_inertia(double x) {
  set_rotational_inertia(x);
}
void car_set_center_to_front(double x) {
  set_center_to_front(x);
}
void car_set_center_to_rear(double x) {
  set_center_to_rear(x);
}
void car_set_stiffness_front(double x) {
  set_stiffness_front(x);
}
void car_set_stiffness_rear(double x) {
  set_stiffness_rear(x);
}
}

const EKF car = {
  .name = "car",
  .kinds = { 25, 24, 30, 26, 27, 29, 28, 31 },
  .feature_kinds = {  },
  .f_fun = car_f_fun,
  .F_fun = car_F_fun,
  .err_fun = car_err_fun,
  .inv_err_fun = car_inv_err_fun,
  .H_mod_fun = car_H_mod_fun,
  .predict = car_predict,
  .hs = {
    { 25, car_h_25 },
    { 24, car_h_24 },
    { 30, car_h_30 },
    { 26, car_h_26 },
    { 27, car_h_27 },
    { 29, car_h_29 },
    { 28, car_h_28 },
    { 31, car_h_31 },
  },
  .Hs = {
    { 25, car_H_25 },
    { 24, car_H_24 },
    { 30, car_H_30 },
    { 26, car_H_26 },
    { 27, car_H_27 },
    { 29, car_H_29 },
    { 28, car_H_28 },
    { 31, car_H_31 },
  },
  .updates = {
    { 25, car_update_25 },
    { 24, car_update_24 },
    { 30, car_update_30 },
    { 26, car_update_26 },
    { 27, car_update_27 },
    { 29, car_update_29 },
    { 28, car_update_28 },
    { 31, car_update_31 },
  },
  .Hes = {
  },
  .sets = {
    { "mass", car_set_mass },
    { "rotational_inertia", car_set_rotational_inertia },
    { "center_to_front", car_set_center_to_front },
    { "center_to_rear", car_set_center_to_rear },
    { "stiffness_front", car_set_stiffness_front },
    { "stiffness_rear", car_set_stiffness_rear },
  },
  .extra_routines = {
  },
};

ekf_lib_init(car)
