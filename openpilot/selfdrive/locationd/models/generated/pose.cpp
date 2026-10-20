#include "pose.h"

namespace {
#define DIM 18
#define EDIM 18
#define MEDIM 18
typedef void (*Hfun)(double *, double *, double *);
const static double MAHA_THRESH_4 = 7.814727903251177;
const static double MAHA_THRESH_10 = 7.814727903251177;
const static double MAHA_THRESH_13 = 7.814727903251177;
const static double MAHA_THRESH_14 = 7.814727903251177;

/******************************************************************************
 *                      Code generated with SymPy 1.14.0                      *
 *                                                                            *
 *              See http://www.sympy.org/ for more information.               *
 *                                                                            *
 *                         This file is part of 'ekf'                         *
 ******************************************************************************/
void err_fun(double *nom_x, double *delta_x, double *out_3785433574795897669) {
   out_3785433574795897669[0] = delta_x[0] + nom_x[0];
   out_3785433574795897669[1] = delta_x[1] + nom_x[1];
   out_3785433574795897669[2] = delta_x[2] + nom_x[2];
   out_3785433574795897669[3] = delta_x[3] + nom_x[3];
   out_3785433574795897669[4] = delta_x[4] + nom_x[4];
   out_3785433574795897669[5] = delta_x[5] + nom_x[5];
   out_3785433574795897669[6] = delta_x[6] + nom_x[6];
   out_3785433574795897669[7] = delta_x[7] + nom_x[7];
   out_3785433574795897669[8] = delta_x[8] + nom_x[8];
   out_3785433574795897669[9] = delta_x[9] + nom_x[9];
   out_3785433574795897669[10] = delta_x[10] + nom_x[10];
   out_3785433574795897669[11] = delta_x[11] + nom_x[11];
   out_3785433574795897669[12] = delta_x[12] + nom_x[12];
   out_3785433574795897669[13] = delta_x[13] + nom_x[13];
   out_3785433574795897669[14] = delta_x[14] + nom_x[14];
   out_3785433574795897669[15] = delta_x[15] + nom_x[15];
   out_3785433574795897669[16] = delta_x[16] + nom_x[16];
   out_3785433574795897669[17] = delta_x[17] + nom_x[17];
}
void inv_err_fun(double *nom_x, double *true_x, double *out_9212012821640774097) {
   out_9212012821640774097[0] = -nom_x[0] + true_x[0];
   out_9212012821640774097[1] = -nom_x[1] + true_x[1];
   out_9212012821640774097[2] = -nom_x[2] + true_x[2];
   out_9212012821640774097[3] = -nom_x[3] + true_x[3];
   out_9212012821640774097[4] = -nom_x[4] + true_x[4];
   out_9212012821640774097[5] = -nom_x[5] + true_x[5];
   out_9212012821640774097[6] = -nom_x[6] + true_x[6];
   out_9212012821640774097[7] = -nom_x[7] + true_x[7];
   out_9212012821640774097[8] = -nom_x[8] + true_x[8];
   out_9212012821640774097[9] = -nom_x[9] + true_x[9];
   out_9212012821640774097[10] = -nom_x[10] + true_x[10];
   out_9212012821640774097[11] = -nom_x[11] + true_x[11];
   out_9212012821640774097[12] = -nom_x[12] + true_x[12];
   out_9212012821640774097[13] = -nom_x[13] + true_x[13];
   out_9212012821640774097[14] = -nom_x[14] + true_x[14];
   out_9212012821640774097[15] = -nom_x[15] + true_x[15];
   out_9212012821640774097[16] = -nom_x[16] + true_x[16];
   out_9212012821640774097[17] = -nom_x[17] + true_x[17];
}
void H_mod_fun(double *state, double *out_8403579557236007405) {
   out_8403579557236007405[0] = 1.0;
   out_8403579557236007405[1] = 0.0;
   out_8403579557236007405[2] = 0.0;
   out_8403579557236007405[3] = 0.0;
   out_8403579557236007405[4] = 0.0;
   out_8403579557236007405[5] = 0.0;
   out_8403579557236007405[6] = 0.0;
   out_8403579557236007405[7] = 0.0;
   out_8403579557236007405[8] = 0.0;
   out_8403579557236007405[9] = 0.0;
   out_8403579557236007405[10] = 0.0;
   out_8403579557236007405[11] = 0.0;
   out_8403579557236007405[12] = 0.0;
   out_8403579557236007405[13] = 0.0;
   out_8403579557236007405[14] = 0.0;
   out_8403579557236007405[15] = 0.0;
   out_8403579557236007405[16] = 0.0;
   out_8403579557236007405[17] = 0.0;
   out_8403579557236007405[18] = 0.0;
   out_8403579557236007405[19] = 1.0;
   out_8403579557236007405[20] = 0.0;
   out_8403579557236007405[21] = 0.0;
   out_8403579557236007405[22] = 0.0;
   out_8403579557236007405[23] = 0.0;
   out_8403579557236007405[24] = 0.0;
   out_8403579557236007405[25] = 0.0;
   out_8403579557236007405[26] = 0.0;
   out_8403579557236007405[27] = 0.0;
   out_8403579557236007405[28] = 0.0;
   out_8403579557236007405[29] = 0.0;
   out_8403579557236007405[30] = 0.0;
   out_8403579557236007405[31] = 0.0;
   out_8403579557236007405[32] = 0.0;
   out_8403579557236007405[33] = 0.0;
   out_8403579557236007405[34] = 0.0;
   out_8403579557236007405[35] = 0.0;
   out_8403579557236007405[36] = 0.0;
   out_8403579557236007405[37] = 0.0;
   out_8403579557236007405[38] = 1.0;
   out_8403579557236007405[39] = 0.0;
   out_8403579557236007405[40] = 0.0;
   out_8403579557236007405[41] = 0.0;
   out_8403579557236007405[42] = 0.0;
   out_8403579557236007405[43] = 0.0;
   out_8403579557236007405[44] = 0.0;
   out_8403579557236007405[45] = 0.0;
   out_8403579557236007405[46] = 0.0;
   out_8403579557236007405[47] = 0.0;
   out_8403579557236007405[48] = 0.0;
   out_8403579557236007405[49] = 0.0;
   out_8403579557236007405[50] = 0.0;
   out_8403579557236007405[51] = 0.0;
   out_8403579557236007405[52] = 0.0;
   out_8403579557236007405[53] = 0.0;
   out_8403579557236007405[54] = 0.0;
   out_8403579557236007405[55] = 0.0;
   out_8403579557236007405[56] = 0.0;
   out_8403579557236007405[57] = 1.0;
   out_8403579557236007405[58] = 0.0;
   out_8403579557236007405[59] = 0.0;
   out_8403579557236007405[60] = 0.0;
   out_8403579557236007405[61] = 0.0;
   out_8403579557236007405[62] = 0.0;
   out_8403579557236007405[63] = 0.0;
   out_8403579557236007405[64] = 0.0;
   out_8403579557236007405[65] = 0.0;
   out_8403579557236007405[66] = 0.0;
   out_8403579557236007405[67] = 0.0;
   out_8403579557236007405[68] = 0.0;
   out_8403579557236007405[69] = 0.0;
   out_8403579557236007405[70] = 0.0;
   out_8403579557236007405[71] = 0.0;
   out_8403579557236007405[72] = 0.0;
   out_8403579557236007405[73] = 0.0;
   out_8403579557236007405[74] = 0.0;
   out_8403579557236007405[75] = 0.0;
   out_8403579557236007405[76] = 1.0;
   out_8403579557236007405[77] = 0.0;
   out_8403579557236007405[78] = 0.0;
   out_8403579557236007405[79] = 0.0;
   out_8403579557236007405[80] = 0.0;
   out_8403579557236007405[81] = 0.0;
   out_8403579557236007405[82] = 0.0;
   out_8403579557236007405[83] = 0.0;
   out_8403579557236007405[84] = 0.0;
   out_8403579557236007405[85] = 0.0;
   out_8403579557236007405[86] = 0.0;
   out_8403579557236007405[87] = 0.0;
   out_8403579557236007405[88] = 0.0;
   out_8403579557236007405[89] = 0.0;
   out_8403579557236007405[90] = 0.0;
   out_8403579557236007405[91] = 0.0;
   out_8403579557236007405[92] = 0.0;
   out_8403579557236007405[93] = 0.0;
   out_8403579557236007405[94] = 0.0;
   out_8403579557236007405[95] = 1.0;
   out_8403579557236007405[96] = 0.0;
   out_8403579557236007405[97] = 0.0;
   out_8403579557236007405[98] = 0.0;
   out_8403579557236007405[99] = 0.0;
   out_8403579557236007405[100] = 0.0;
   out_8403579557236007405[101] = 0.0;
   out_8403579557236007405[102] = 0.0;
   out_8403579557236007405[103] = 0.0;
   out_8403579557236007405[104] = 0.0;
   out_8403579557236007405[105] = 0.0;
   out_8403579557236007405[106] = 0.0;
   out_8403579557236007405[107] = 0.0;
   out_8403579557236007405[108] = 0.0;
   out_8403579557236007405[109] = 0.0;
   out_8403579557236007405[110] = 0.0;
   out_8403579557236007405[111] = 0.0;
   out_8403579557236007405[112] = 0.0;
   out_8403579557236007405[113] = 0.0;
   out_8403579557236007405[114] = 1.0;
   out_8403579557236007405[115] = 0.0;
   out_8403579557236007405[116] = 0.0;
   out_8403579557236007405[117] = 0.0;
   out_8403579557236007405[118] = 0.0;
   out_8403579557236007405[119] = 0.0;
   out_8403579557236007405[120] = 0.0;
   out_8403579557236007405[121] = 0.0;
   out_8403579557236007405[122] = 0.0;
   out_8403579557236007405[123] = 0.0;
   out_8403579557236007405[124] = 0.0;
   out_8403579557236007405[125] = 0.0;
   out_8403579557236007405[126] = 0.0;
   out_8403579557236007405[127] = 0.0;
   out_8403579557236007405[128] = 0.0;
   out_8403579557236007405[129] = 0.0;
   out_8403579557236007405[130] = 0.0;
   out_8403579557236007405[131] = 0.0;
   out_8403579557236007405[132] = 0.0;
   out_8403579557236007405[133] = 1.0;
   out_8403579557236007405[134] = 0.0;
   out_8403579557236007405[135] = 0.0;
   out_8403579557236007405[136] = 0.0;
   out_8403579557236007405[137] = 0.0;
   out_8403579557236007405[138] = 0.0;
   out_8403579557236007405[139] = 0.0;
   out_8403579557236007405[140] = 0.0;
   out_8403579557236007405[141] = 0.0;
   out_8403579557236007405[142] = 0.0;
   out_8403579557236007405[143] = 0.0;
   out_8403579557236007405[144] = 0.0;
   out_8403579557236007405[145] = 0.0;
   out_8403579557236007405[146] = 0.0;
   out_8403579557236007405[147] = 0.0;
   out_8403579557236007405[148] = 0.0;
   out_8403579557236007405[149] = 0.0;
   out_8403579557236007405[150] = 0.0;
   out_8403579557236007405[151] = 0.0;
   out_8403579557236007405[152] = 1.0;
   out_8403579557236007405[153] = 0.0;
   out_8403579557236007405[154] = 0.0;
   out_8403579557236007405[155] = 0.0;
   out_8403579557236007405[156] = 0.0;
   out_8403579557236007405[157] = 0.0;
   out_8403579557236007405[158] = 0.0;
   out_8403579557236007405[159] = 0.0;
   out_8403579557236007405[160] = 0.0;
   out_8403579557236007405[161] = 0.0;
   out_8403579557236007405[162] = 0.0;
   out_8403579557236007405[163] = 0.0;
   out_8403579557236007405[164] = 0.0;
   out_8403579557236007405[165] = 0.0;
   out_8403579557236007405[166] = 0.0;
   out_8403579557236007405[167] = 0.0;
   out_8403579557236007405[168] = 0.0;
   out_8403579557236007405[169] = 0.0;
   out_8403579557236007405[170] = 0.0;
   out_8403579557236007405[171] = 1.0;
   out_8403579557236007405[172] = 0.0;
   out_8403579557236007405[173] = 0.0;
   out_8403579557236007405[174] = 0.0;
   out_8403579557236007405[175] = 0.0;
   out_8403579557236007405[176] = 0.0;
   out_8403579557236007405[177] = 0.0;
   out_8403579557236007405[178] = 0.0;
   out_8403579557236007405[179] = 0.0;
   out_8403579557236007405[180] = 0.0;
   out_8403579557236007405[181] = 0.0;
   out_8403579557236007405[182] = 0.0;
   out_8403579557236007405[183] = 0.0;
   out_8403579557236007405[184] = 0.0;
   out_8403579557236007405[185] = 0.0;
   out_8403579557236007405[186] = 0.0;
   out_8403579557236007405[187] = 0.0;
   out_8403579557236007405[188] = 0.0;
   out_8403579557236007405[189] = 0.0;
   out_8403579557236007405[190] = 1.0;
   out_8403579557236007405[191] = 0.0;
   out_8403579557236007405[192] = 0.0;
   out_8403579557236007405[193] = 0.0;
   out_8403579557236007405[194] = 0.0;
   out_8403579557236007405[195] = 0.0;
   out_8403579557236007405[196] = 0.0;
   out_8403579557236007405[197] = 0.0;
   out_8403579557236007405[198] = 0.0;
   out_8403579557236007405[199] = 0.0;
   out_8403579557236007405[200] = 0.0;
   out_8403579557236007405[201] = 0.0;
   out_8403579557236007405[202] = 0.0;
   out_8403579557236007405[203] = 0.0;
   out_8403579557236007405[204] = 0.0;
   out_8403579557236007405[205] = 0.0;
   out_8403579557236007405[206] = 0.0;
   out_8403579557236007405[207] = 0.0;
   out_8403579557236007405[208] = 0.0;
   out_8403579557236007405[209] = 1.0;
   out_8403579557236007405[210] = 0.0;
   out_8403579557236007405[211] = 0.0;
   out_8403579557236007405[212] = 0.0;
   out_8403579557236007405[213] = 0.0;
   out_8403579557236007405[214] = 0.0;
   out_8403579557236007405[215] = 0.0;
   out_8403579557236007405[216] = 0.0;
   out_8403579557236007405[217] = 0.0;
   out_8403579557236007405[218] = 0.0;
   out_8403579557236007405[219] = 0.0;
   out_8403579557236007405[220] = 0.0;
   out_8403579557236007405[221] = 0.0;
   out_8403579557236007405[222] = 0.0;
   out_8403579557236007405[223] = 0.0;
   out_8403579557236007405[224] = 0.0;
   out_8403579557236007405[225] = 0.0;
   out_8403579557236007405[226] = 0.0;
   out_8403579557236007405[227] = 0.0;
   out_8403579557236007405[228] = 1.0;
   out_8403579557236007405[229] = 0.0;
   out_8403579557236007405[230] = 0.0;
   out_8403579557236007405[231] = 0.0;
   out_8403579557236007405[232] = 0.0;
   out_8403579557236007405[233] = 0.0;
   out_8403579557236007405[234] = 0.0;
   out_8403579557236007405[235] = 0.0;
   out_8403579557236007405[236] = 0.0;
   out_8403579557236007405[237] = 0.0;
   out_8403579557236007405[238] = 0.0;
   out_8403579557236007405[239] = 0.0;
   out_8403579557236007405[240] = 0.0;
   out_8403579557236007405[241] = 0.0;
   out_8403579557236007405[242] = 0.0;
   out_8403579557236007405[243] = 0.0;
   out_8403579557236007405[244] = 0.0;
   out_8403579557236007405[245] = 0.0;
   out_8403579557236007405[246] = 0.0;
   out_8403579557236007405[247] = 1.0;
   out_8403579557236007405[248] = 0.0;
   out_8403579557236007405[249] = 0.0;
   out_8403579557236007405[250] = 0.0;
   out_8403579557236007405[251] = 0.0;
   out_8403579557236007405[252] = 0.0;
   out_8403579557236007405[253] = 0.0;
   out_8403579557236007405[254] = 0.0;
   out_8403579557236007405[255] = 0.0;
   out_8403579557236007405[256] = 0.0;
   out_8403579557236007405[257] = 0.0;
   out_8403579557236007405[258] = 0.0;
   out_8403579557236007405[259] = 0.0;
   out_8403579557236007405[260] = 0.0;
   out_8403579557236007405[261] = 0.0;
   out_8403579557236007405[262] = 0.0;
   out_8403579557236007405[263] = 0.0;
   out_8403579557236007405[264] = 0.0;
   out_8403579557236007405[265] = 0.0;
   out_8403579557236007405[266] = 1.0;
   out_8403579557236007405[267] = 0.0;
   out_8403579557236007405[268] = 0.0;
   out_8403579557236007405[269] = 0.0;
   out_8403579557236007405[270] = 0.0;
   out_8403579557236007405[271] = 0.0;
   out_8403579557236007405[272] = 0.0;
   out_8403579557236007405[273] = 0.0;
   out_8403579557236007405[274] = 0.0;
   out_8403579557236007405[275] = 0.0;
   out_8403579557236007405[276] = 0.0;
   out_8403579557236007405[277] = 0.0;
   out_8403579557236007405[278] = 0.0;
   out_8403579557236007405[279] = 0.0;
   out_8403579557236007405[280] = 0.0;
   out_8403579557236007405[281] = 0.0;
   out_8403579557236007405[282] = 0.0;
   out_8403579557236007405[283] = 0.0;
   out_8403579557236007405[284] = 0.0;
   out_8403579557236007405[285] = 1.0;
   out_8403579557236007405[286] = 0.0;
   out_8403579557236007405[287] = 0.0;
   out_8403579557236007405[288] = 0.0;
   out_8403579557236007405[289] = 0.0;
   out_8403579557236007405[290] = 0.0;
   out_8403579557236007405[291] = 0.0;
   out_8403579557236007405[292] = 0.0;
   out_8403579557236007405[293] = 0.0;
   out_8403579557236007405[294] = 0.0;
   out_8403579557236007405[295] = 0.0;
   out_8403579557236007405[296] = 0.0;
   out_8403579557236007405[297] = 0.0;
   out_8403579557236007405[298] = 0.0;
   out_8403579557236007405[299] = 0.0;
   out_8403579557236007405[300] = 0.0;
   out_8403579557236007405[301] = 0.0;
   out_8403579557236007405[302] = 0.0;
   out_8403579557236007405[303] = 0.0;
   out_8403579557236007405[304] = 1.0;
   out_8403579557236007405[305] = 0.0;
   out_8403579557236007405[306] = 0.0;
   out_8403579557236007405[307] = 0.0;
   out_8403579557236007405[308] = 0.0;
   out_8403579557236007405[309] = 0.0;
   out_8403579557236007405[310] = 0.0;
   out_8403579557236007405[311] = 0.0;
   out_8403579557236007405[312] = 0.0;
   out_8403579557236007405[313] = 0.0;
   out_8403579557236007405[314] = 0.0;
   out_8403579557236007405[315] = 0.0;
   out_8403579557236007405[316] = 0.0;
   out_8403579557236007405[317] = 0.0;
   out_8403579557236007405[318] = 0.0;
   out_8403579557236007405[319] = 0.0;
   out_8403579557236007405[320] = 0.0;
   out_8403579557236007405[321] = 0.0;
   out_8403579557236007405[322] = 0.0;
   out_8403579557236007405[323] = 1.0;
}
void f_fun(double *state, double dt, double *out_3020321548497812838) {
   out_3020321548497812838[0] = atan2((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), -(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]));
   out_3020321548497812838[1] = asin(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]));
   out_3020321548497812838[2] = atan2(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), -(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]));
   out_3020321548497812838[3] = dt*state[12] + state[3];
   out_3020321548497812838[4] = dt*state[13] + state[4];
   out_3020321548497812838[5] = dt*state[14] + state[5];
   out_3020321548497812838[6] = state[6];
   out_3020321548497812838[7] = state[7];
   out_3020321548497812838[8] = state[8];
   out_3020321548497812838[9] = state[9];
   out_3020321548497812838[10] = state[10];
   out_3020321548497812838[11] = state[11];
   out_3020321548497812838[12] = state[12];
   out_3020321548497812838[13] = state[13];
   out_3020321548497812838[14] = state[14];
   out_3020321548497812838[15] = state[15];
   out_3020321548497812838[16] = state[16];
   out_3020321548497812838[17] = state[17];
}
void F_fun(double *state, double dt, double *out_1603619229747962468) {
   out_1603619229747962468[0] = ((-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*cos(state[0])*cos(state[1]) - sin(state[0])*cos(dt*state[6])*cos(dt*state[7])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + ((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*cos(state[0])*cos(state[1]) - sin(dt*state[6])*sin(state[0])*cos(dt*state[7])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_1603619229747962468[1] = ((-sin(dt*state[6])*sin(dt*state[8]) - sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*cos(state[1]) - (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*sin(state[1]) - sin(state[1])*cos(dt*state[6])*cos(dt*state[7])*cos(state[0]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*sin(state[1]) + (-sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) + sin(dt*state[8])*cos(dt*state[6]))*cos(state[1]) - sin(dt*state[6])*sin(state[1])*cos(dt*state[7])*cos(state[0]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_1603619229747962468[2] = 0;
   out_1603619229747962468[3] = 0;
   out_1603619229747962468[4] = 0;
   out_1603619229747962468[5] = 0;
   out_1603619229747962468[6] = (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(dt*cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*sin(dt*state[8]) - dt*sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-dt*sin(dt*state[6])*cos(dt*state[8]) + dt*sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) - dt*cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (dt*sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_1603619229747962468[7] = (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[6])*sin(dt*state[7])*cos(state[0])*cos(state[1]) + dt*sin(dt*state[6])*sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) - dt*sin(dt*state[6])*sin(state[1])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[7])*cos(dt*state[6])*cos(state[0])*cos(state[1]) + dt*sin(dt*state[8])*sin(state[0])*cos(dt*state[6])*cos(dt*state[7])*cos(state[1]) - dt*sin(state[1])*cos(dt*state[6])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_1603619229747962468[8] = ((dt*sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + dt*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (dt*sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + ((dt*sin(dt*state[6])*sin(dt*state[8]) + dt*sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*cos(dt*state[8]) + dt*sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_1603619229747962468[9] = 0;
   out_1603619229747962468[10] = 0;
   out_1603619229747962468[11] = 0;
   out_1603619229747962468[12] = 0;
   out_1603619229747962468[13] = 0;
   out_1603619229747962468[14] = 0;
   out_1603619229747962468[15] = 0;
   out_1603619229747962468[16] = 0;
   out_1603619229747962468[17] = 0;
   out_1603619229747962468[18] = (-sin(dt*state[7])*sin(state[0])*cos(state[1]) - sin(dt*state[8])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_1603619229747962468[19] = (-sin(dt*state[7])*sin(state[1])*cos(state[0]) + sin(dt*state[8])*sin(state[0])*sin(state[1])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_1603619229747962468[20] = 0;
   out_1603619229747962468[21] = 0;
   out_1603619229747962468[22] = 0;
   out_1603619229747962468[23] = 0;
   out_1603619229747962468[24] = 0;
   out_1603619229747962468[25] = (dt*sin(dt*state[7])*sin(dt*state[8])*sin(state[0])*cos(state[1]) - dt*sin(dt*state[7])*sin(state[1])*cos(dt*state[8]) + dt*cos(dt*state[7])*cos(state[0])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_1603619229747962468[26] = (-dt*sin(dt*state[8])*sin(state[1])*cos(dt*state[7]) - dt*sin(state[0])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_1603619229747962468[27] = 0;
   out_1603619229747962468[28] = 0;
   out_1603619229747962468[29] = 0;
   out_1603619229747962468[30] = 0;
   out_1603619229747962468[31] = 0;
   out_1603619229747962468[32] = 0;
   out_1603619229747962468[33] = 0;
   out_1603619229747962468[34] = 0;
   out_1603619229747962468[35] = 0;
   out_1603619229747962468[36] = ((sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[7]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[7]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_1603619229747962468[37] = (-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(-sin(dt*state[7])*sin(state[2])*cos(state[0])*cos(state[1]) + sin(dt*state[8])*sin(state[0])*sin(state[2])*cos(dt*state[7])*cos(state[1]) - sin(state[1])*sin(state[2])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*(-sin(dt*state[7])*cos(state[0])*cos(state[1])*cos(state[2]) + sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1])*cos(state[2]) - sin(state[1])*cos(dt*state[7])*cos(dt*state[8])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_1603619229747962468[38] = ((-sin(state[0])*sin(state[2]) - sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (-sin(state[0])*sin(state[1])*sin(state[2]) - cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_1603619229747962468[39] = 0;
   out_1603619229747962468[40] = 0;
   out_1603619229747962468[41] = 0;
   out_1603619229747962468[42] = 0;
   out_1603619229747962468[43] = (-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(dt*(sin(state[0])*cos(state[2]) - sin(state[1])*sin(state[2])*cos(state[0]))*cos(dt*state[7]) - dt*(sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[7])*sin(dt*state[8]) - dt*sin(dt*state[7])*sin(state[2])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*(dt*(-sin(state[0])*sin(state[2]) - sin(state[1])*cos(state[0])*cos(state[2]))*cos(dt*state[7]) - dt*(sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[7])*sin(dt*state[8]) - dt*sin(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_1603619229747962468[44] = (dt*(sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*cos(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*sin(state[2])*cos(dt*state[7])*cos(state[1]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + (dt*(sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*cos(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[7])*cos(state[1])*cos(state[2]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_1603619229747962468[45] = 0;
   out_1603619229747962468[46] = 0;
   out_1603619229747962468[47] = 0;
   out_1603619229747962468[48] = 0;
   out_1603619229747962468[49] = 0;
   out_1603619229747962468[50] = 0;
   out_1603619229747962468[51] = 0;
   out_1603619229747962468[52] = 0;
   out_1603619229747962468[53] = 0;
   out_1603619229747962468[54] = 0;
   out_1603619229747962468[55] = 0;
   out_1603619229747962468[56] = 0;
   out_1603619229747962468[57] = 1;
   out_1603619229747962468[58] = 0;
   out_1603619229747962468[59] = 0;
   out_1603619229747962468[60] = 0;
   out_1603619229747962468[61] = 0;
   out_1603619229747962468[62] = 0;
   out_1603619229747962468[63] = 0;
   out_1603619229747962468[64] = 0;
   out_1603619229747962468[65] = 0;
   out_1603619229747962468[66] = dt;
   out_1603619229747962468[67] = 0;
   out_1603619229747962468[68] = 0;
   out_1603619229747962468[69] = 0;
   out_1603619229747962468[70] = 0;
   out_1603619229747962468[71] = 0;
   out_1603619229747962468[72] = 0;
   out_1603619229747962468[73] = 0;
   out_1603619229747962468[74] = 0;
   out_1603619229747962468[75] = 0;
   out_1603619229747962468[76] = 1;
   out_1603619229747962468[77] = 0;
   out_1603619229747962468[78] = 0;
   out_1603619229747962468[79] = 0;
   out_1603619229747962468[80] = 0;
   out_1603619229747962468[81] = 0;
   out_1603619229747962468[82] = 0;
   out_1603619229747962468[83] = 0;
   out_1603619229747962468[84] = 0;
   out_1603619229747962468[85] = dt;
   out_1603619229747962468[86] = 0;
   out_1603619229747962468[87] = 0;
   out_1603619229747962468[88] = 0;
   out_1603619229747962468[89] = 0;
   out_1603619229747962468[90] = 0;
   out_1603619229747962468[91] = 0;
   out_1603619229747962468[92] = 0;
   out_1603619229747962468[93] = 0;
   out_1603619229747962468[94] = 0;
   out_1603619229747962468[95] = 1;
   out_1603619229747962468[96] = 0;
   out_1603619229747962468[97] = 0;
   out_1603619229747962468[98] = 0;
   out_1603619229747962468[99] = 0;
   out_1603619229747962468[100] = 0;
   out_1603619229747962468[101] = 0;
   out_1603619229747962468[102] = 0;
   out_1603619229747962468[103] = 0;
   out_1603619229747962468[104] = dt;
   out_1603619229747962468[105] = 0;
   out_1603619229747962468[106] = 0;
   out_1603619229747962468[107] = 0;
   out_1603619229747962468[108] = 0;
   out_1603619229747962468[109] = 0;
   out_1603619229747962468[110] = 0;
   out_1603619229747962468[111] = 0;
   out_1603619229747962468[112] = 0;
   out_1603619229747962468[113] = 0;
   out_1603619229747962468[114] = 1;
   out_1603619229747962468[115] = 0;
   out_1603619229747962468[116] = 0;
   out_1603619229747962468[117] = 0;
   out_1603619229747962468[118] = 0;
   out_1603619229747962468[119] = 0;
   out_1603619229747962468[120] = 0;
   out_1603619229747962468[121] = 0;
   out_1603619229747962468[122] = 0;
   out_1603619229747962468[123] = 0;
   out_1603619229747962468[124] = 0;
   out_1603619229747962468[125] = 0;
   out_1603619229747962468[126] = 0;
   out_1603619229747962468[127] = 0;
   out_1603619229747962468[128] = 0;
   out_1603619229747962468[129] = 0;
   out_1603619229747962468[130] = 0;
   out_1603619229747962468[131] = 0;
   out_1603619229747962468[132] = 0;
   out_1603619229747962468[133] = 1;
   out_1603619229747962468[134] = 0;
   out_1603619229747962468[135] = 0;
   out_1603619229747962468[136] = 0;
   out_1603619229747962468[137] = 0;
   out_1603619229747962468[138] = 0;
   out_1603619229747962468[139] = 0;
   out_1603619229747962468[140] = 0;
   out_1603619229747962468[141] = 0;
   out_1603619229747962468[142] = 0;
   out_1603619229747962468[143] = 0;
   out_1603619229747962468[144] = 0;
   out_1603619229747962468[145] = 0;
   out_1603619229747962468[146] = 0;
   out_1603619229747962468[147] = 0;
   out_1603619229747962468[148] = 0;
   out_1603619229747962468[149] = 0;
   out_1603619229747962468[150] = 0;
   out_1603619229747962468[151] = 0;
   out_1603619229747962468[152] = 1;
   out_1603619229747962468[153] = 0;
   out_1603619229747962468[154] = 0;
   out_1603619229747962468[155] = 0;
   out_1603619229747962468[156] = 0;
   out_1603619229747962468[157] = 0;
   out_1603619229747962468[158] = 0;
   out_1603619229747962468[159] = 0;
   out_1603619229747962468[160] = 0;
   out_1603619229747962468[161] = 0;
   out_1603619229747962468[162] = 0;
   out_1603619229747962468[163] = 0;
   out_1603619229747962468[164] = 0;
   out_1603619229747962468[165] = 0;
   out_1603619229747962468[166] = 0;
   out_1603619229747962468[167] = 0;
   out_1603619229747962468[168] = 0;
   out_1603619229747962468[169] = 0;
   out_1603619229747962468[170] = 0;
   out_1603619229747962468[171] = 1;
   out_1603619229747962468[172] = 0;
   out_1603619229747962468[173] = 0;
   out_1603619229747962468[174] = 0;
   out_1603619229747962468[175] = 0;
   out_1603619229747962468[176] = 0;
   out_1603619229747962468[177] = 0;
   out_1603619229747962468[178] = 0;
   out_1603619229747962468[179] = 0;
   out_1603619229747962468[180] = 0;
   out_1603619229747962468[181] = 0;
   out_1603619229747962468[182] = 0;
   out_1603619229747962468[183] = 0;
   out_1603619229747962468[184] = 0;
   out_1603619229747962468[185] = 0;
   out_1603619229747962468[186] = 0;
   out_1603619229747962468[187] = 0;
   out_1603619229747962468[188] = 0;
   out_1603619229747962468[189] = 0;
   out_1603619229747962468[190] = 1;
   out_1603619229747962468[191] = 0;
   out_1603619229747962468[192] = 0;
   out_1603619229747962468[193] = 0;
   out_1603619229747962468[194] = 0;
   out_1603619229747962468[195] = 0;
   out_1603619229747962468[196] = 0;
   out_1603619229747962468[197] = 0;
   out_1603619229747962468[198] = 0;
   out_1603619229747962468[199] = 0;
   out_1603619229747962468[200] = 0;
   out_1603619229747962468[201] = 0;
   out_1603619229747962468[202] = 0;
   out_1603619229747962468[203] = 0;
   out_1603619229747962468[204] = 0;
   out_1603619229747962468[205] = 0;
   out_1603619229747962468[206] = 0;
   out_1603619229747962468[207] = 0;
   out_1603619229747962468[208] = 0;
   out_1603619229747962468[209] = 1;
   out_1603619229747962468[210] = 0;
   out_1603619229747962468[211] = 0;
   out_1603619229747962468[212] = 0;
   out_1603619229747962468[213] = 0;
   out_1603619229747962468[214] = 0;
   out_1603619229747962468[215] = 0;
   out_1603619229747962468[216] = 0;
   out_1603619229747962468[217] = 0;
   out_1603619229747962468[218] = 0;
   out_1603619229747962468[219] = 0;
   out_1603619229747962468[220] = 0;
   out_1603619229747962468[221] = 0;
   out_1603619229747962468[222] = 0;
   out_1603619229747962468[223] = 0;
   out_1603619229747962468[224] = 0;
   out_1603619229747962468[225] = 0;
   out_1603619229747962468[226] = 0;
   out_1603619229747962468[227] = 0;
   out_1603619229747962468[228] = 1;
   out_1603619229747962468[229] = 0;
   out_1603619229747962468[230] = 0;
   out_1603619229747962468[231] = 0;
   out_1603619229747962468[232] = 0;
   out_1603619229747962468[233] = 0;
   out_1603619229747962468[234] = 0;
   out_1603619229747962468[235] = 0;
   out_1603619229747962468[236] = 0;
   out_1603619229747962468[237] = 0;
   out_1603619229747962468[238] = 0;
   out_1603619229747962468[239] = 0;
   out_1603619229747962468[240] = 0;
   out_1603619229747962468[241] = 0;
   out_1603619229747962468[242] = 0;
   out_1603619229747962468[243] = 0;
   out_1603619229747962468[244] = 0;
   out_1603619229747962468[245] = 0;
   out_1603619229747962468[246] = 0;
   out_1603619229747962468[247] = 1;
   out_1603619229747962468[248] = 0;
   out_1603619229747962468[249] = 0;
   out_1603619229747962468[250] = 0;
   out_1603619229747962468[251] = 0;
   out_1603619229747962468[252] = 0;
   out_1603619229747962468[253] = 0;
   out_1603619229747962468[254] = 0;
   out_1603619229747962468[255] = 0;
   out_1603619229747962468[256] = 0;
   out_1603619229747962468[257] = 0;
   out_1603619229747962468[258] = 0;
   out_1603619229747962468[259] = 0;
   out_1603619229747962468[260] = 0;
   out_1603619229747962468[261] = 0;
   out_1603619229747962468[262] = 0;
   out_1603619229747962468[263] = 0;
   out_1603619229747962468[264] = 0;
   out_1603619229747962468[265] = 0;
   out_1603619229747962468[266] = 1;
   out_1603619229747962468[267] = 0;
   out_1603619229747962468[268] = 0;
   out_1603619229747962468[269] = 0;
   out_1603619229747962468[270] = 0;
   out_1603619229747962468[271] = 0;
   out_1603619229747962468[272] = 0;
   out_1603619229747962468[273] = 0;
   out_1603619229747962468[274] = 0;
   out_1603619229747962468[275] = 0;
   out_1603619229747962468[276] = 0;
   out_1603619229747962468[277] = 0;
   out_1603619229747962468[278] = 0;
   out_1603619229747962468[279] = 0;
   out_1603619229747962468[280] = 0;
   out_1603619229747962468[281] = 0;
   out_1603619229747962468[282] = 0;
   out_1603619229747962468[283] = 0;
   out_1603619229747962468[284] = 0;
   out_1603619229747962468[285] = 1;
   out_1603619229747962468[286] = 0;
   out_1603619229747962468[287] = 0;
   out_1603619229747962468[288] = 0;
   out_1603619229747962468[289] = 0;
   out_1603619229747962468[290] = 0;
   out_1603619229747962468[291] = 0;
   out_1603619229747962468[292] = 0;
   out_1603619229747962468[293] = 0;
   out_1603619229747962468[294] = 0;
   out_1603619229747962468[295] = 0;
   out_1603619229747962468[296] = 0;
   out_1603619229747962468[297] = 0;
   out_1603619229747962468[298] = 0;
   out_1603619229747962468[299] = 0;
   out_1603619229747962468[300] = 0;
   out_1603619229747962468[301] = 0;
   out_1603619229747962468[302] = 0;
   out_1603619229747962468[303] = 0;
   out_1603619229747962468[304] = 1;
   out_1603619229747962468[305] = 0;
   out_1603619229747962468[306] = 0;
   out_1603619229747962468[307] = 0;
   out_1603619229747962468[308] = 0;
   out_1603619229747962468[309] = 0;
   out_1603619229747962468[310] = 0;
   out_1603619229747962468[311] = 0;
   out_1603619229747962468[312] = 0;
   out_1603619229747962468[313] = 0;
   out_1603619229747962468[314] = 0;
   out_1603619229747962468[315] = 0;
   out_1603619229747962468[316] = 0;
   out_1603619229747962468[317] = 0;
   out_1603619229747962468[318] = 0;
   out_1603619229747962468[319] = 0;
   out_1603619229747962468[320] = 0;
   out_1603619229747962468[321] = 0;
   out_1603619229747962468[322] = 0;
   out_1603619229747962468[323] = 1;
}
void h_4(double *state, double *unused, double *out_2763600513678111825) {
   out_2763600513678111825[0] = state[6] + state[9];
   out_2763600513678111825[1] = state[7] + state[10];
   out_2763600513678111825[2] = state[8] + state[11];
}
void H_4(double *state, double *unused, double *out_3299554532568645259) {
   out_3299554532568645259[0] = 0;
   out_3299554532568645259[1] = 0;
   out_3299554532568645259[2] = 0;
   out_3299554532568645259[3] = 0;
   out_3299554532568645259[4] = 0;
   out_3299554532568645259[5] = 0;
   out_3299554532568645259[6] = 1;
   out_3299554532568645259[7] = 0;
   out_3299554532568645259[8] = 0;
   out_3299554532568645259[9] = 1;
   out_3299554532568645259[10] = 0;
   out_3299554532568645259[11] = 0;
   out_3299554532568645259[12] = 0;
   out_3299554532568645259[13] = 0;
   out_3299554532568645259[14] = 0;
   out_3299554532568645259[15] = 0;
   out_3299554532568645259[16] = 0;
   out_3299554532568645259[17] = 0;
   out_3299554532568645259[18] = 0;
   out_3299554532568645259[19] = 0;
   out_3299554532568645259[20] = 0;
   out_3299554532568645259[21] = 0;
   out_3299554532568645259[22] = 0;
   out_3299554532568645259[23] = 0;
   out_3299554532568645259[24] = 0;
   out_3299554532568645259[25] = 1;
   out_3299554532568645259[26] = 0;
   out_3299554532568645259[27] = 0;
   out_3299554532568645259[28] = 1;
   out_3299554532568645259[29] = 0;
   out_3299554532568645259[30] = 0;
   out_3299554532568645259[31] = 0;
   out_3299554532568645259[32] = 0;
   out_3299554532568645259[33] = 0;
   out_3299554532568645259[34] = 0;
   out_3299554532568645259[35] = 0;
   out_3299554532568645259[36] = 0;
   out_3299554532568645259[37] = 0;
   out_3299554532568645259[38] = 0;
   out_3299554532568645259[39] = 0;
   out_3299554532568645259[40] = 0;
   out_3299554532568645259[41] = 0;
   out_3299554532568645259[42] = 0;
   out_3299554532568645259[43] = 0;
   out_3299554532568645259[44] = 1;
   out_3299554532568645259[45] = 0;
   out_3299554532568645259[46] = 0;
   out_3299554532568645259[47] = 1;
   out_3299554532568645259[48] = 0;
   out_3299554532568645259[49] = 0;
   out_3299554532568645259[50] = 0;
   out_3299554532568645259[51] = 0;
   out_3299554532568645259[52] = 0;
   out_3299554532568645259[53] = 0;
}
void h_10(double *state, double *unused, double *out_6934731533478205261) {
   out_6934731533478205261[0] = 9.8100000000000005*sin(state[1]) - state[4]*state[8] + state[5]*state[7] + state[12] + state[15];
   out_6934731533478205261[1] = -9.8100000000000005*sin(state[0])*cos(state[1]) + state[3]*state[8] - state[5]*state[6] + state[13] + state[16];
   out_6934731533478205261[2] = -9.8100000000000005*cos(state[0])*cos(state[1]) - state[3]*state[7] + state[4]*state[6] + state[14] + state[17];
}
void H_10(double *state, double *unused, double *out_6963337135212532460) {
   out_6963337135212532460[0] = 0;
   out_6963337135212532460[1] = 9.8100000000000005*cos(state[1]);
   out_6963337135212532460[2] = 0;
   out_6963337135212532460[3] = 0;
   out_6963337135212532460[4] = -state[8];
   out_6963337135212532460[5] = state[7];
   out_6963337135212532460[6] = 0;
   out_6963337135212532460[7] = state[5];
   out_6963337135212532460[8] = -state[4];
   out_6963337135212532460[9] = 0;
   out_6963337135212532460[10] = 0;
   out_6963337135212532460[11] = 0;
   out_6963337135212532460[12] = 1;
   out_6963337135212532460[13] = 0;
   out_6963337135212532460[14] = 0;
   out_6963337135212532460[15] = 1;
   out_6963337135212532460[16] = 0;
   out_6963337135212532460[17] = 0;
   out_6963337135212532460[18] = -9.8100000000000005*cos(state[0])*cos(state[1]);
   out_6963337135212532460[19] = 9.8100000000000005*sin(state[0])*sin(state[1]);
   out_6963337135212532460[20] = 0;
   out_6963337135212532460[21] = state[8];
   out_6963337135212532460[22] = 0;
   out_6963337135212532460[23] = -state[6];
   out_6963337135212532460[24] = -state[5];
   out_6963337135212532460[25] = 0;
   out_6963337135212532460[26] = state[3];
   out_6963337135212532460[27] = 0;
   out_6963337135212532460[28] = 0;
   out_6963337135212532460[29] = 0;
   out_6963337135212532460[30] = 0;
   out_6963337135212532460[31] = 1;
   out_6963337135212532460[32] = 0;
   out_6963337135212532460[33] = 0;
   out_6963337135212532460[34] = 1;
   out_6963337135212532460[35] = 0;
   out_6963337135212532460[36] = 9.8100000000000005*sin(state[0])*cos(state[1]);
   out_6963337135212532460[37] = 9.8100000000000005*sin(state[1])*cos(state[0]);
   out_6963337135212532460[38] = 0;
   out_6963337135212532460[39] = -state[7];
   out_6963337135212532460[40] = state[6];
   out_6963337135212532460[41] = 0;
   out_6963337135212532460[42] = state[4];
   out_6963337135212532460[43] = -state[3];
   out_6963337135212532460[44] = 0;
   out_6963337135212532460[45] = 0;
   out_6963337135212532460[46] = 0;
   out_6963337135212532460[47] = 0;
   out_6963337135212532460[48] = 0;
   out_6963337135212532460[49] = 0;
   out_6963337135212532460[50] = 1;
   out_6963337135212532460[51] = 0;
   out_6963337135212532460[52] = 0;
   out_6963337135212532460[53] = 1;
}
void h_13(double *state, double *unused, double *out_6337999574759843798) {
   out_6337999574759843798[0] = state[3];
   out_6337999574759843798[1] = state[4];
   out_6337999574759843798[2] = state[5];
}
void H_13(double *state, double *unused, double *out_4311076675748055670) {
   out_4311076675748055670[0] = 0;
   out_4311076675748055670[1] = 0;
   out_4311076675748055670[2] = 0;
   out_4311076675748055670[3] = 1;
   out_4311076675748055670[4] = 0;
   out_4311076675748055670[5] = 0;
   out_4311076675748055670[6] = 0;
   out_4311076675748055670[7] = 0;
   out_4311076675748055670[8] = 0;
   out_4311076675748055670[9] = 0;
   out_4311076675748055670[10] = 0;
   out_4311076675748055670[11] = 0;
   out_4311076675748055670[12] = 0;
   out_4311076675748055670[13] = 0;
   out_4311076675748055670[14] = 0;
   out_4311076675748055670[15] = 0;
   out_4311076675748055670[16] = 0;
   out_4311076675748055670[17] = 0;
   out_4311076675748055670[18] = 0;
   out_4311076675748055670[19] = 0;
   out_4311076675748055670[20] = 0;
   out_4311076675748055670[21] = 0;
   out_4311076675748055670[22] = 1;
   out_4311076675748055670[23] = 0;
   out_4311076675748055670[24] = 0;
   out_4311076675748055670[25] = 0;
   out_4311076675748055670[26] = 0;
   out_4311076675748055670[27] = 0;
   out_4311076675748055670[28] = 0;
   out_4311076675748055670[29] = 0;
   out_4311076675748055670[30] = 0;
   out_4311076675748055670[31] = 0;
   out_4311076675748055670[32] = 0;
   out_4311076675748055670[33] = 0;
   out_4311076675748055670[34] = 0;
   out_4311076675748055670[35] = 0;
   out_4311076675748055670[36] = 0;
   out_4311076675748055670[37] = 0;
   out_4311076675748055670[38] = 0;
   out_4311076675748055670[39] = 0;
   out_4311076675748055670[40] = 0;
   out_4311076675748055670[41] = 1;
   out_4311076675748055670[42] = 0;
   out_4311076675748055670[43] = 0;
   out_4311076675748055670[44] = 0;
   out_4311076675748055670[45] = 0;
   out_4311076675748055670[46] = 0;
   out_4311076675748055670[47] = 0;
   out_4311076675748055670[48] = 0;
   out_4311076675748055670[49] = 0;
   out_4311076675748055670[50] = 0;
   out_4311076675748055670[51] = 0;
   out_4311076675748055670[52] = 0;
   out_4311076675748055670[53] = 0;
}
void h_14(double *state, double *unused, double *out_5026526532466082050) {
   out_5026526532466082050[0] = state[6];
   out_5026526532466082050[1] = state[7];
   out_5026526532466082050[2] = state[8];
}
void H_14(double *state, double *unused, double *out_663686323770839270) {
   out_663686323770839270[0] = 0;
   out_663686323770839270[1] = 0;
   out_663686323770839270[2] = 0;
   out_663686323770839270[3] = 0;
   out_663686323770839270[4] = 0;
   out_663686323770839270[5] = 0;
   out_663686323770839270[6] = 1;
   out_663686323770839270[7] = 0;
   out_663686323770839270[8] = 0;
   out_663686323770839270[9] = 0;
   out_663686323770839270[10] = 0;
   out_663686323770839270[11] = 0;
   out_663686323770839270[12] = 0;
   out_663686323770839270[13] = 0;
   out_663686323770839270[14] = 0;
   out_663686323770839270[15] = 0;
   out_663686323770839270[16] = 0;
   out_663686323770839270[17] = 0;
   out_663686323770839270[18] = 0;
   out_663686323770839270[19] = 0;
   out_663686323770839270[20] = 0;
   out_663686323770839270[21] = 0;
   out_663686323770839270[22] = 0;
   out_663686323770839270[23] = 0;
   out_663686323770839270[24] = 0;
   out_663686323770839270[25] = 1;
   out_663686323770839270[26] = 0;
   out_663686323770839270[27] = 0;
   out_663686323770839270[28] = 0;
   out_663686323770839270[29] = 0;
   out_663686323770839270[30] = 0;
   out_663686323770839270[31] = 0;
   out_663686323770839270[32] = 0;
   out_663686323770839270[33] = 0;
   out_663686323770839270[34] = 0;
   out_663686323770839270[35] = 0;
   out_663686323770839270[36] = 0;
   out_663686323770839270[37] = 0;
   out_663686323770839270[38] = 0;
   out_663686323770839270[39] = 0;
   out_663686323770839270[40] = 0;
   out_663686323770839270[41] = 0;
   out_663686323770839270[42] = 0;
   out_663686323770839270[43] = 0;
   out_663686323770839270[44] = 1;
   out_663686323770839270[45] = 0;
   out_663686323770839270[46] = 0;
   out_663686323770839270[47] = 0;
   out_663686323770839270[48] = 0;
   out_663686323770839270[49] = 0;
   out_663686323770839270[50] = 0;
   out_663686323770839270[51] = 0;
   out_663686323770839270[52] = 0;
   out_663686323770839270[53] = 0;
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

void pose_update_4(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<3, 3, 0>(in_x, in_P, h_4, H_4, NULL, in_z, in_R, in_ea, MAHA_THRESH_4);
}
void pose_update_10(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<3, 3, 0>(in_x, in_P, h_10, H_10, NULL, in_z, in_R, in_ea, MAHA_THRESH_10);
}
void pose_update_13(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<3, 3, 0>(in_x, in_P, h_13, H_13, NULL, in_z, in_R, in_ea, MAHA_THRESH_13);
}
void pose_update_14(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<3, 3, 0>(in_x, in_P, h_14, H_14, NULL, in_z, in_R, in_ea, MAHA_THRESH_14);
}
void pose_err_fun(double *nom_x, double *delta_x, double *out_3785433574795897669) {
  err_fun(nom_x, delta_x, out_3785433574795897669);
}
void pose_inv_err_fun(double *nom_x, double *true_x, double *out_9212012821640774097) {
  inv_err_fun(nom_x, true_x, out_9212012821640774097);
}
void pose_H_mod_fun(double *state, double *out_8403579557236007405) {
  H_mod_fun(state, out_8403579557236007405);
}
void pose_f_fun(double *state, double dt, double *out_3020321548497812838) {
  f_fun(state,  dt, out_3020321548497812838);
}
void pose_F_fun(double *state, double dt, double *out_1603619229747962468) {
  F_fun(state,  dt, out_1603619229747962468);
}
void pose_h_4(double *state, double *unused, double *out_2763600513678111825) {
  h_4(state, unused, out_2763600513678111825);
}
void pose_H_4(double *state, double *unused, double *out_3299554532568645259) {
  H_4(state, unused, out_3299554532568645259);
}
void pose_h_10(double *state, double *unused, double *out_6934731533478205261) {
  h_10(state, unused, out_6934731533478205261);
}
void pose_H_10(double *state, double *unused, double *out_6963337135212532460) {
  H_10(state, unused, out_6963337135212532460);
}
void pose_h_13(double *state, double *unused, double *out_6337999574759843798) {
  h_13(state, unused, out_6337999574759843798);
}
void pose_H_13(double *state, double *unused, double *out_4311076675748055670) {
  H_13(state, unused, out_4311076675748055670);
}
void pose_h_14(double *state, double *unused, double *out_5026526532466082050) {
  h_14(state, unused, out_5026526532466082050);
}
void pose_H_14(double *state, double *unused, double *out_663686323770839270) {
  H_14(state, unused, out_663686323770839270);
}
void pose_predict(double *in_x, double *in_P, double *in_Q, double dt) {
  predict(in_x, in_P, in_Q, dt);
}
}

const EKF pose = {
  .name = "pose",
  .kinds = { 4, 10, 13, 14 },
  .feature_kinds = {  },
  .f_fun = pose_f_fun,
  .F_fun = pose_F_fun,
  .err_fun = pose_err_fun,
  .inv_err_fun = pose_inv_err_fun,
  .H_mod_fun = pose_H_mod_fun,
  .predict = pose_predict,
  .hs = {
    { 4, pose_h_4 },
    { 10, pose_h_10 },
    { 13, pose_h_13 },
    { 14, pose_h_14 },
  },
  .Hs = {
    { 4, pose_H_4 },
    { 10, pose_H_10 },
    { 13, pose_H_13 },
    { 14, pose_H_14 },
  },
  .updates = {
    { 4, pose_update_4 },
    { 10, pose_update_10 },
    { 13, pose_update_13 },
    { 14, pose_update_14 },
  },
  .Hes = {
  },
  .sets = {
  },
  .extra_routines = {
  },
};

ekf_lib_init(pose)
