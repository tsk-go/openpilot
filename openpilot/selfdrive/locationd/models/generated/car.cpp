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
void err_fun(double *nom_x, double *delta_x, double *out_3470217287287697986) {
   out_3470217287287697986[0] = delta_x[0] + nom_x[0];
   out_3470217287287697986[1] = delta_x[1] + nom_x[1];
   out_3470217287287697986[2] = delta_x[2] + nom_x[2];
   out_3470217287287697986[3] = delta_x[3] + nom_x[3];
   out_3470217287287697986[4] = delta_x[4] + nom_x[4];
   out_3470217287287697986[5] = delta_x[5] + nom_x[5];
   out_3470217287287697986[6] = delta_x[6] + nom_x[6];
   out_3470217287287697986[7] = delta_x[7] + nom_x[7];
   out_3470217287287697986[8] = delta_x[8] + nom_x[8];
}
void inv_err_fun(double *nom_x, double *true_x, double *out_5423086811818805380) {
   out_5423086811818805380[0] = -nom_x[0] + true_x[0];
   out_5423086811818805380[1] = -nom_x[1] + true_x[1];
   out_5423086811818805380[2] = -nom_x[2] + true_x[2];
   out_5423086811818805380[3] = -nom_x[3] + true_x[3];
   out_5423086811818805380[4] = -nom_x[4] + true_x[4];
   out_5423086811818805380[5] = -nom_x[5] + true_x[5];
   out_5423086811818805380[6] = -nom_x[6] + true_x[6];
   out_5423086811818805380[7] = -nom_x[7] + true_x[7];
   out_5423086811818805380[8] = -nom_x[8] + true_x[8];
}
void H_mod_fun(double *state, double *out_8859145476210338021) {
   out_8859145476210338021[0] = 1.0;
   out_8859145476210338021[1] = 0.0;
   out_8859145476210338021[2] = 0.0;
   out_8859145476210338021[3] = 0.0;
   out_8859145476210338021[4] = 0.0;
   out_8859145476210338021[5] = 0.0;
   out_8859145476210338021[6] = 0.0;
   out_8859145476210338021[7] = 0.0;
   out_8859145476210338021[8] = 0.0;
   out_8859145476210338021[9] = 0.0;
   out_8859145476210338021[10] = 1.0;
   out_8859145476210338021[11] = 0.0;
   out_8859145476210338021[12] = 0.0;
   out_8859145476210338021[13] = 0.0;
   out_8859145476210338021[14] = 0.0;
   out_8859145476210338021[15] = 0.0;
   out_8859145476210338021[16] = 0.0;
   out_8859145476210338021[17] = 0.0;
   out_8859145476210338021[18] = 0.0;
   out_8859145476210338021[19] = 0.0;
   out_8859145476210338021[20] = 1.0;
   out_8859145476210338021[21] = 0.0;
   out_8859145476210338021[22] = 0.0;
   out_8859145476210338021[23] = 0.0;
   out_8859145476210338021[24] = 0.0;
   out_8859145476210338021[25] = 0.0;
   out_8859145476210338021[26] = 0.0;
   out_8859145476210338021[27] = 0.0;
   out_8859145476210338021[28] = 0.0;
   out_8859145476210338021[29] = 0.0;
   out_8859145476210338021[30] = 1.0;
   out_8859145476210338021[31] = 0.0;
   out_8859145476210338021[32] = 0.0;
   out_8859145476210338021[33] = 0.0;
   out_8859145476210338021[34] = 0.0;
   out_8859145476210338021[35] = 0.0;
   out_8859145476210338021[36] = 0.0;
   out_8859145476210338021[37] = 0.0;
   out_8859145476210338021[38] = 0.0;
   out_8859145476210338021[39] = 0.0;
   out_8859145476210338021[40] = 1.0;
   out_8859145476210338021[41] = 0.0;
   out_8859145476210338021[42] = 0.0;
   out_8859145476210338021[43] = 0.0;
   out_8859145476210338021[44] = 0.0;
   out_8859145476210338021[45] = 0.0;
   out_8859145476210338021[46] = 0.0;
   out_8859145476210338021[47] = 0.0;
   out_8859145476210338021[48] = 0.0;
   out_8859145476210338021[49] = 0.0;
   out_8859145476210338021[50] = 1.0;
   out_8859145476210338021[51] = 0.0;
   out_8859145476210338021[52] = 0.0;
   out_8859145476210338021[53] = 0.0;
   out_8859145476210338021[54] = 0.0;
   out_8859145476210338021[55] = 0.0;
   out_8859145476210338021[56] = 0.0;
   out_8859145476210338021[57] = 0.0;
   out_8859145476210338021[58] = 0.0;
   out_8859145476210338021[59] = 0.0;
   out_8859145476210338021[60] = 1.0;
   out_8859145476210338021[61] = 0.0;
   out_8859145476210338021[62] = 0.0;
   out_8859145476210338021[63] = 0.0;
   out_8859145476210338021[64] = 0.0;
   out_8859145476210338021[65] = 0.0;
   out_8859145476210338021[66] = 0.0;
   out_8859145476210338021[67] = 0.0;
   out_8859145476210338021[68] = 0.0;
   out_8859145476210338021[69] = 0.0;
   out_8859145476210338021[70] = 1.0;
   out_8859145476210338021[71] = 0.0;
   out_8859145476210338021[72] = 0.0;
   out_8859145476210338021[73] = 0.0;
   out_8859145476210338021[74] = 0.0;
   out_8859145476210338021[75] = 0.0;
   out_8859145476210338021[76] = 0.0;
   out_8859145476210338021[77] = 0.0;
   out_8859145476210338021[78] = 0.0;
   out_8859145476210338021[79] = 0.0;
   out_8859145476210338021[80] = 1.0;
}
void f_fun(double *state, double dt, double *out_4364048461385736387) {
   out_4364048461385736387[0] = state[0];
   out_4364048461385736387[1] = state[1];
   out_4364048461385736387[2] = state[2];
   out_4364048461385736387[3] = state[3];
   out_4364048461385736387[4] = state[4];
   out_4364048461385736387[5] = dt*((-state[4] + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(mass*state[4]))*state[6] - 9.8100000000000005*state[8] + stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(mass*state[1]) + (-stiffness_front*state[0] - stiffness_rear*state[0])*state[5]/(mass*state[4])) + state[5];
   out_4364048461385736387[6] = dt*(center_to_front*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(rotational_inertia*state[1]) + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])*state[5]/(rotational_inertia*state[4]) + (-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])*state[6]/(rotational_inertia*state[4])) + state[6];
   out_4364048461385736387[7] = state[7];
   out_4364048461385736387[8] = state[8];
}
void F_fun(double *state, double dt, double *out_5736261136038400283) {
   out_5736261136038400283[0] = 1;
   out_5736261136038400283[1] = 0;
   out_5736261136038400283[2] = 0;
   out_5736261136038400283[3] = 0;
   out_5736261136038400283[4] = 0;
   out_5736261136038400283[5] = 0;
   out_5736261136038400283[6] = 0;
   out_5736261136038400283[7] = 0;
   out_5736261136038400283[8] = 0;
   out_5736261136038400283[9] = 0;
   out_5736261136038400283[10] = 1;
   out_5736261136038400283[11] = 0;
   out_5736261136038400283[12] = 0;
   out_5736261136038400283[13] = 0;
   out_5736261136038400283[14] = 0;
   out_5736261136038400283[15] = 0;
   out_5736261136038400283[16] = 0;
   out_5736261136038400283[17] = 0;
   out_5736261136038400283[18] = 0;
   out_5736261136038400283[19] = 0;
   out_5736261136038400283[20] = 1;
   out_5736261136038400283[21] = 0;
   out_5736261136038400283[22] = 0;
   out_5736261136038400283[23] = 0;
   out_5736261136038400283[24] = 0;
   out_5736261136038400283[25] = 0;
   out_5736261136038400283[26] = 0;
   out_5736261136038400283[27] = 0;
   out_5736261136038400283[28] = 0;
   out_5736261136038400283[29] = 0;
   out_5736261136038400283[30] = 1;
   out_5736261136038400283[31] = 0;
   out_5736261136038400283[32] = 0;
   out_5736261136038400283[33] = 0;
   out_5736261136038400283[34] = 0;
   out_5736261136038400283[35] = 0;
   out_5736261136038400283[36] = 0;
   out_5736261136038400283[37] = 0;
   out_5736261136038400283[38] = 0;
   out_5736261136038400283[39] = 0;
   out_5736261136038400283[40] = 1;
   out_5736261136038400283[41] = 0;
   out_5736261136038400283[42] = 0;
   out_5736261136038400283[43] = 0;
   out_5736261136038400283[44] = 0;
   out_5736261136038400283[45] = dt*(stiffness_front*(-state[2] - state[3] + state[7])/(mass*state[1]) + (-stiffness_front - stiffness_rear)*state[5]/(mass*state[4]) + (-center_to_front*stiffness_front + center_to_rear*stiffness_rear)*state[6]/(mass*state[4]));
   out_5736261136038400283[46] = -dt*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(mass*pow(state[1], 2));
   out_5736261136038400283[47] = -dt*stiffness_front*state[0]/(mass*state[1]);
   out_5736261136038400283[48] = -dt*stiffness_front*state[0]/(mass*state[1]);
   out_5736261136038400283[49] = dt*((-1 - (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(mass*pow(state[4], 2)))*state[6] - (-stiffness_front*state[0] - stiffness_rear*state[0])*state[5]/(mass*pow(state[4], 2)));
   out_5736261136038400283[50] = dt*(-stiffness_front*state[0] - stiffness_rear*state[0])/(mass*state[4]) + 1;
   out_5736261136038400283[51] = dt*(-state[4] + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(mass*state[4]));
   out_5736261136038400283[52] = dt*stiffness_front*state[0]/(mass*state[1]);
   out_5736261136038400283[53] = -9.8100000000000005*dt;
   out_5736261136038400283[54] = dt*(center_to_front*stiffness_front*(-state[2] - state[3] + state[7])/(rotational_inertia*state[1]) + (-center_to_front*stiffness_front + center_to_rear*stiffness_rear)*state[5]/(rotational_inertia*state[4]) + (-pow(center_to_front, 2)*stiffness_front - pow(center_to_rear, 2)*stiffness_rear)*state[6]/(rotational_inertia*state[4]));
   out_5736261136038400283[55] = -center_to_front*dt*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(rotational_inertia*pow(state[1], 2));
   out_5736261136038400283[56] = -center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_5736261136038400283[57] = -center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_5736261136038400283[58] = dt*(-(-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])*state[5]/(rotational_inertia*pow(state[4], 2)) - (-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])*state[6]/(rotational_inertia*pow(state[4], 2)));
   out_5736261136038400283[59] = dt*(-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(rotational_inertia*state[4]);
   out_5736261136038400283[60] = dt*(-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])/(rotational_inertia*state[4]) + 1;
   out_5736261136038400283[61] = center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_5736261136038400283[62] = 0;
   out_5736261136038400283[63] = 0;
   out_5736261136038400283[64] = 0;
   out_5736261136038400283[65] = 0;
   out_5736261136038400283[66] = 0;
   out_5736261136038400283[67] = 0;
   out_5736261136038400283[68] = 0;
   out_5736261136038400283[69] = 0;
   out_5736261136038400283[70] = 1;
   out_5736261136038400283[71] = 0;
   out_5736261136038400283[72] = 0;
   out_5736261136038400283[73] = 0;
   out_5736261136038400283[74] = 0;
   out_5736261136038400283[75] = 0;
   out_5736261136038400283[76] = 0;
   out_5736261136038400283[77] = 0;
   out_5736261136038400283[78] = 0;
   out_5736261136038400283[79] = 0;
   out_5736261136038400283[80] = 1;
}
void h_25(double *state, double *unused, double *out_2839818080272470940) {
   out_2839818080272470940[0] = state[6];
}
void H_25(double *state, double *unused, double *out_6064617947509721918) {
   out_6064617947509721918[0] = 0;
   out_6064617947509721918[1] = 0;
   out_6064617947509721918[2] = 0;
   out_6064617947509721918[3] = 0;
   out_6064617947509721918[4] = 0;
   out_6064617947509721918[5] = 0;
   out_6064617947509721918[6] = 1;
   out_6064617947509721918[7] = 0;
   out_6064617947509721918[8] = 0;
}
void h_24(double *state, double *unused, double *out_6639924414496629328) {
   out_6639924414496629328[0] = state[4];
   out_6639924414496629328[1] = state[5];
}
void H_24(double *state, double *unused, double *out_2506692348707398782) {
   out_2506692348707398782[0] = 0;
   out_2506692348707398782[1] = 0;
   out_2506692348707398782[2] = 0;
   out_2506692348707398782[3] = 0;
   out_2506692348707398782[4] = 1;
   out_2506692348707398782[5] = 0;
   out_2506692348707398782[6] = 0;
   out_2506692348707398782[7] = 0;
   out_2506692348707398782[8] = 0;
   out_2506692348707398782[9] = 0;
   out_2506692348707398782[10] = 0;
   out_2506692348707398782[11] = 0;
   out_2506692348707398782[12] = 0;
   out_2506692348707398782[13] = 0;
   out_2506692348707398782[14] = 1;
   out_2506692348707398782[15] = 0;
   out_2506692348707398782[16] = 0;
   out_2506692348707398782[17] = 0;
}
void h_30(double *state, double *unused, double *out_1319846228188637228) {
   out_1319846228188637228[0] = state[4];
}
void H_30(double *state, double *unused, double *out_7854429796072221500) {
   out_7854429796072221500[0] = 0;
   out_7854429796072221500[1] = 0;
   out_7854429796072221500[2] = 0;
   out_7854429796072221500[3] = 0;
   out_7854429796072221500[4] = 1;
   out_7854429796072221500[5] = 0;
   out_7854429796072221500[6] = 0;
   out_7854429796072221500[7] = 0;
   out_7854429796072221500[8] = 0;
}
void h_26(double *state, double *unused, double *out_7198131715747352316) {
   out_7198131715747352316[0] = state[7];
}
void H_26(double *state, double *unused, double *out_8640622807325773474) {
   out_8640622807325773474[0] = 0;
   out_8640622807325773474[1] = 0;
   out_8640622807325773474[2] = 0;
   out_8640622807325773474[3] = 0;
   out_8640622807325773474[4] = 0;
   out_8640622807325773474[5] = 0;
   out_8640622807325773474[6] = 0;
   out_8640622807325773474[7] = 1;
   out_8640622807325773474[8] = 0;
}
void h_27(double *state, double *unused, double *out_3285488125208824077) {
   out_3285488125208824077[0] = state[3];
}
void H_27(double *state, double *unused, double *out_8368720206453386899) {
   out_8368720206453386899[0] = 0;
   out_8368720206453386899[1] = 0;
   out_8368720206453386899[2] = 0;
   out_8368720206453386899[3] = 1;
   out_8368720206453386899[4] = 0;
   out_8368720206453386899[5] = 0;
   out_8368720206453386899[6] = 0;
   out_8368720206453386899[7] = 0;
   out_8368720206453386899[8] = 0;
}
void h_29(double *state, double *unused, double *out_716530343512159711) {
   out_716530343512159711[0] = state[1];
}
void H_29(double *state, double *unused, double *out_8364661140386613684) {
   out_8364661140386613684[0] = 0;
   out_8364661140386613684[1] = 1;
   out_8364661140386613684[2] = 0;
   out_8364661140386613684[3] = 0;
   out_8364661140386613684[4] = 0;
   out_8364661140386613684[5] = 0;
   out_8364661140386613684[6] = 0;
   out_8364661140386613684[7] = 0;
   out_8364661140386613684[8] = 0;
}
void h_28(double *state, double *unused, double *out_1716185142452021568) {
   out_1716185142452021568[0] = state[0];
}
void H_28(double *state, double *unused, double *out_8118452661757611681) {
   out_8118452661757611681[0] = 1;
   out_8118452661757611681[1] = 0;
   out_8118452661757611681[2] = 0;
   out_8118452661757611681[3] = 0;
   out_8118452661757611681[4] = 0;
   out_8118452661757611681[5] = 0;
   out_8118452661757611681[6] = 0;
   out_8118452661757611681[7] = 0;
   out_8118452661757611681[8] = 0;
}
void h_31(double *state, double *unused, double *out_4542766280828628078) {
   out_4542766280828628078[0] = state[8];
}
void H_31(double *state, double *unused, double *out_8014414705092421998) {
   out_8014414705092421998[0] = 0;
   out_8014414705092421998[1] = 0;
   out_8014414705092421998[2] = 0;
   out_8014414705092421998[3] = 0;
   out_8014414705092421998[4] = 0;
   out_8014414705092421998[5] = 0;
   out_8014414705092421998[6] = 0;
   out_8014414705092421998[7] = 0;
   out_8014414705092421998[8] = 1;
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
void car_err_fun(double *nom_x, double *delta_x, double *out_3470217287287697986) {
  err_fun(nom_x, delta_x, out_3470217287287697986);
}
void car_inv_err_fun(double *nom_x, double *true_x, double *out_5423086811818805380) {
  inv_err_fun(nom_x, true_x, out_5423086811818805380);
}
void car_H_mod_fun(double *state, double *out_8859145476210338021) {
  H_mod_fun(state, out_8859145476210338021);
}
void car_f_fun(double *state, double dt, double *out_4364048461385736387) {
  f_fun(state,  dt, out_4364048461385736387);
}
void car_F_fun(double *state, double dt, double *out_5736261136038400283) {
  F_fun(state,  dt, out_5736261136038400283);
}
void car_h_25(double *state, double *unused, double *out_2839818080272470940) {
  h_25(state, unused, out_2839818080272470940);
}
void car_H_25(double *state, double *unused, double *out_6064617947509721918) {
  H_25(state, unused, out_6064617947509721918);
}
void car_h_24(double *state, double *unused, double *out_6639924414496629328) {
  h_24(state, unused, out_6639924414496629328);
}
void car_H_24(double *state, double *unused, double *out_2506692348707398782) {
  H_24(state, unused, out_2506692348707398782);
}
void car_h_30(double *state, double *unused, double *out_1319846228188637228) {
  h_30(state, unused, out_1319846228188637228);
}
void car_H_30(double *state, double *unused, double *out_7854429796072221500) {
  H_30(state, unused, out_7854429796072221500);
}
void car_h_26(double *state, double *unused, double *out_7198131715747352316) {
  h_26(state, unused, out_7198131715747352316);
}
void car_H_26(double *state, double *unused, double *out_8640622807325773474) {
  H_26(state, unused, out_8640622807325773474);
}
void car_h_27(double *state, double *unused, double *out_3285488125208824077) {
  h_27(state, unused, out_3285488125208824077);
}
void car_H_27(double *state, double *unused, double *out_8368720206453386899) {
  H_27(state, unused, out_8368720206453386899);
}
void car_h_29(double *state, double *unused, double *out_716530343512159711) {
  h_29(state, unused, out_716530343512159711);
}
void car_H_29(double *state, double *unused, double *out_8364661140386613684) {
  H_29(state, unused, out_8364661140386613684);
}
void car_h_28(double *state, double *unused, double *out_1716185142452021568) {
  h_28(state, unused, out_1716185142452021568);
}
void car_H_28(double *state, double *unused, double *out_8118452661757611681) {
  H_28(state, unused, out_8118452661757611681);
}
void car_h_31(double *state, double *unused, double *out_4542766280828628078) {
  h_31(state, unused, out_4542766280828628078);
}
void car_H_31(double *state, double *unused, double *out_8014414705092421998) {
  H_31(state, unused, out_8014414705092421998);
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
