#pragma once
#include "rednose/helpers/ekf.h"
extern "C" {
void car_update_25(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_24(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_30(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_26(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_27(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_29(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_28(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_31(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_err_fun(double *nom_x, double *delta_x, double *out_2648765499125548386);
void car_inv_err_fun(double *nom_x, double *true_x, double *out_4382045588843432432);
void car_H_mod_fun(double *state, double *out_2251915477403000420);
void car_f_fun(double *state, double dt, double *out_4522542339241629323);
void car_F_fun(double *state, double dt, double *out_7592860940737014978);
void car_h_25(double *state, double *unused, double *out_5554548494829736911);
void car_H_25(double *state, double *unused, double *out_2651776347781664420);
void car_h_24(double *state, double *unused, double *out_6096955322389461271);
void car_H_24(double *state, double *unused, double *out_9219395919336369095);
void car_h_30(double *state, double *unused, double *out_4395534897616074713);
void car_H_30(double *state, double *unused, double *out_8878277384436270441);
void car_h_26(double *state, double *unused, double *out_749355165499572824);
void car_H_26(double *state, double *unused, double *out_1089726971092391804);
void car_h_27(double *state, double *unused, double *out_4572464401494438799);
void car_H_27(double *state, double *unused, double *out_7393703377472856264);
void car_h_29(double *state, double *unused, double *out_9049535908432631258);
void car_H_29(double *state, double *unused, double *out_5680340650603305231);
void car_h_28(double *state, double *unused, double *out_3969148516817961282);
void car_H_28(double *state, double *unused, double *out_597941633533774657);
void car_h_31(double *state, double *unused, double *out_5829742557114242800);
void car_H_31(double *state, double *unused, double *out_2682422309658624848);
void car_predict(double *in_x, double *in_P, double *in_Q, double dt);
void car_set_mass(double x);
void car_set_rotational_inertia(double x);
void car_set_center_to_front(double x);
void car_set_center_to_rear(double x);
void car_set_stiffness_front(double x);
void car_set_stiffness_rear(double x);
}