#pragma once
#include "rednose/helpers/ekf.h"
extern "C" {
void pose_update_4(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_10(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_13(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_14(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_err_fun(double *nom_x, double *delta_x, double *out_6609500045983475884);
void pose_inv_err_fun(double *nom_x, double *true_x, double *out_2251582086712269854);
void pose_H_mod_fun(double *state, double *out_8200145802550385466);
void pose_f_fun(double *state, double dt, double *out_3154493756264028272);
void pose_F_fun(double *state, double dt, double *out_3844222318897373612);
void pose_h_4(double *state, double *unused, double *out_7417392044831538702);
void pose_H_4(double *state, double *unused, double *out_744215863507435876);
void pose_h_10(double *state, double *unused, double *out_5837768205443090035);
void pose_H_10(double *state, double *unused, double *out_6045792490383943628);
void pose_h_13(double *state, double *unused, double *out_886522868392701902);
void pose_H_13(double *state, double *unused, double *out_2468057961824896925);
void pose_h_14(double *state, double *unused, double *out_8921497272601995159);
void pose_H_14(double *state, double *unused, double *out_8225361678787176300);
void pose_predict(double *in_x, double *in_P, double *in_Q, double dt);
}