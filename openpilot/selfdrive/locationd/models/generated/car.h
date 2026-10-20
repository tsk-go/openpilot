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
void car_err_fun(double *nom_x, double *delta_x, double *out_5507159804932095856);
void car_inv_err_fun(double *nom_x, double *true_x, double *out_3708402617549620907);
void car_H_mod_fun(double *state, double *out_3048507717174445082);
void car_f_fun(double *state, double dt, double *out_2392350810154680862);
void car_F_fun(double *state, double dt, double *out_3545351747806026181);
void car_h_25(double *state, double *unused, double *out_100883961627628976);
void car_H_25(double *state, double *unused, double *out_7952199542359109922);
void car_h_24(double *state, double *unused, double *out_8651264488955021024);
void car_H_24(double *state, double *unused, double *out_3918972724758923593);
void car_h_30(double *state, double *unused, double *out_975203001893898031);
void car_H_30(double *state, double *unused, double *out_7976211572843193067);
void car_h_26(double *state, double *unused, double *out_5976876269554743676);
void car_H_26(double *state, double *unused, double *out_4210696223485053698);
void car_h_27(double *state, double *unused, double *out_4900789306033216669);
void car_H_27(double *state, double *unused, double *out_5752617501659249850);
void car_h_29(double *state, double *unused, double *out_1918712854795560466);
void car_H_29(double *state, double *unused, double *out_7465980228528800883);
void car_h_28(double *state, double *unused, double *out_7903224896595378112);
void car_H_28(double *state, double *unused, double *out_5898364828111220159);
void car_h_31(double *state, double *unused, double *out_7662381295193043465);
void car_H_31(double *state, double *unused, double *out_7982845504236070350);
void car_predict(double *in_x, double *in_P, double *in_Q, double dt);
void car_set_mass(double x);
void car_set_rotational_inertia(double x);
void car_set_center_to_front(double x);
void car_set_center_to_rear(double x);
void car_set_stiffness_front(double x);
void car_set_stiffness_rear(double x);
}