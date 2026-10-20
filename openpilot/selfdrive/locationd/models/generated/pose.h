#pragma once
#include "rednose/helpers/ekf.h"
extern "C" {
void pose_update_4(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_10(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_13(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_14(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_err_fun(double *nom_x, double *delta_x, double *out_3785433574795897669);
void pose_inv_err_fun(double *nom_x, double *true_x, double *out_9212012821640774097);
void pose_H_mod_fun(double *state, double *out_8403579557236007405);
void pose_f_fun(double *state, double dt, double *out_3020321548497812838);
void pose_F_fun(double *state, double dt, double *out_1603619229747962468);
void pose_h_4(double *state, double *unused, double *out_2763600513678111825);
void pose_H_4(double *state, double *unused, double *out_3299554532568645259);
void pose_h_10(double *state, double *unused, double *out_6934731533478205261);
void pose_H_10(double *state, double *unused, double *out_6963337135212532460);
void pose_h_13(double *state, double *unused, double *out_6337999574759843798);
void pose_H_13(double *state, double *unused, double *out_4311076675748055670);
void pose_h_14(double *state, double *unused, double *out_5026526532466082050);
void pose_H_14(double *state, double *unused, double *out_663686323770839270);
void pose_predict(double *in_x, double *in_P, double *in_Q, double dt);
}