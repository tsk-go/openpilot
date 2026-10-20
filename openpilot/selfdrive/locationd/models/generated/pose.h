#pragma once
#include "rednose/helpers/ekf.h"
extern "C" {
void pose_update_4(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_10(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_13(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_14(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_err_fun(double *nom_x, double *delta_x, double *out_6205306553489213410);
void pose_inv_err_fun(double *nom_x, double *true_x, double *out_1970164945047322285);
void pose_H_mod_fun(double *state, double *out_755526174421445756);
void pose_f_fun(double *state, double dt, double *out_3677371884399014073);
void pose_F_fun(double *state, double dt, double *out_663397675647970276);
void pose_h_4(double *state, double *unused, double *out_7443258878815348214);
void pose_H_4(double *state, double *unused, double *out_442421307461452348);
void pose_h_10(double *state, double *unused, double *out_6538590839038528319);
void pose_H_10(double *state, double *unused, double *out_1931000376780675843);
void pose_h_13(double *state, double *unused, double *out_5562882792733924299);
void pose_H_13(double *state, double *unused, double *out_3654695132793785149);
void pose_h_14(double *state, double *unused, double *out_7679846457276660545);
void pose_H_14(double *state, double *unused, double *out_4405662163800936877);
void pose_predict(double *in_x, double *in_P, double *in_Q, double dt);
}