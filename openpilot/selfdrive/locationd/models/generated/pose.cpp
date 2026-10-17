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
void err_fun(double *nom_x, double *delta_x, double *out_6609500045983475884) {
   out_6609500045983475884[0] = delta_x[0] + nom_x[0];
   out_6609500045983475884[1] = delta_x[1] + nom_x[1];
   out_6609500045983475884[2] = delta_x[2] + nom_x[2];
   out_6609500045983475884[3] = delta_x[3] + nom_x[3];
   out_6609500045983475884[4] = delta_x[4] + nom_x[4];
   out_6609500045983475884[5] = delta_x[5] + nom_x[5];
   out_6609500045983475884[6] = delta_x[6] + nom_x[6];
   out_6609500045983475884[7] = delta_x[7] + nom_x[7];
   out_6609500045983475884[8] = delta_x[8] + nom_x[8];
   out_6609500045983475884[9] = delta_x[9] + nom_x[9];
   out_6609500045983475884[10] = delta_x[10] + nom_x[10];
   out_6609500045983475884[11] = delta_x[11] + nom_x[11];
   out_6609500045983475884[12] = delta_x[12] + nom_x[12];
   out_6609500045983475884[13] = delta_x[13] + nom_x[13];
   out_6609500045983475884[14] = delta_x[14] + nom_x[14];
   out_6609500045983475884[15] = delta_x[15] + nom_x[15];
   out_6609500045983475884[16] = delta_x[16] + nom_x[16];
   out_6609500045983475884[17] = delta_x[17] + nom_x[17];
}
void inv_err_fun(double *nom_x, double *true_x, double *out_2251582086712269854) {
   out_2251582086712269854[0] = -nom_x[0] + true_x[0];
   out_2251582086712269854[1] = -nom_x[1] + true_x[1];
   out_2251582086712269854[2] = -nom_x[2] + true_x[2];
   out_2251582086712269854[3] = -nom_x[3] + true_x[3];
   out_2251582086712269854[4] = -nom_x[4] + true_x[4];
   out_2251582086712269854[5] = -nom_x[5] + true_x[5];
   out_2251582086712269854[6] = -nom_x[6] + true_x[6];
   out_2251582086712269854[7] = -nom_x[7] + true_x[7];
   out_2251582086712269854[8] = -nom_x[8] + true_x[8];
   out_2251582086712269854[9] = -nom_x[9] + true_x[9];
   out_2251582086712269854[10] = -nom_x[10] + true_x[10];
   out_2251582086712269854[11] = -nom_x[11] + true_x[11];
   out_2251582086712269854[12] = -nom_x[12] + true_x[12];
   out_2251582086712269854[13] = -nom_x[13] + true_x[13];
   out_2251582086712269854[14] = -nom_x[14] + true_x[14];
   out_2251582086712269854[15] = -nom_x[15] + true_x[15];
   out_2251582086712269854[16] = -nom_x[16] + true_x[16];
   out_2251582086712269854[17] = -nom_x[17] + true_x[17];
}
void H_mod_fun(double *state, double *out_8200145802550385466) {
   out_8200145802550385466[0] = 1.0;
   out_8200145802550385466[1] = 0.0;
   out_8200145802550385466[2] = 0.0;
   out_8200145802550385466[3] = 0.0;
   out_8200145802550385466[4] = 0.0;
   out_8200145802550385466[5] = 0.0;
   out_8200145802550385466[6] = 0.0;
   out_8200145802550385466[7] = 0.0;
   out_8200145802550385466[8] = 0.0;
   out_8200145802550385466[9] = 0.0;
   out_8200145802550385466[10] = 0.0;
   out_8200145802550385466[11] = 0.0;
   out_8200145802550385466[12] = 0.0;
   out_8200145802550385466[13] = 0.0;
   out_8200145802550385466[14] = 0.0;
   out_8200145802550385466[15] = 0.0;
   out_8200145802550385466[16] = 0.0;
   out_8200145802550385466[17] = 0.0;
   out_8200145802550385466[18] = 0.0;
   out_8200145802550385466[19] = 1.0;
   out_8200145802550385466[20] = 0.0;
   out_8200145802550385466[21] = 0.0;
   out_8200145802550385466[22] = 0.0;
   out_8200145802550385466[23] = 0.0;
   out_8200145802550385466[24] = 0.0;
   out_8200145802550385466[25] = 0.0;
   out_8200145802550385466[26] = 0.0;
   out_8200145802550385466[27] = 0.0;
   out_8200145802550385466[28] = 0.0;
   out_8200145802550385466[29] = 0.0;
   out_8200145802550385466[30] = 0.0;
   out_8200145802550385466[31] = 0.0;
   out_8200145802550385466[32] = 0.0;
   out_8200145802550385466[33] = 0.0;
   out_8200145802550385466[34] = 0.0;
   out_8200145802550385466[35] = 0.0;
   out_8200145802550385466[36] = 0.0;
   out_8200145802550385466[37] = 0.0;
   out_8200145802550385466[38] = 1.0;
   out_8200145802550385466[39] = 0.0;
   out_8200145802550385466[40] = 0.0;
   out_8200145802550385466[41] = 0.0;
   out_8200145802550385466[42] = 0.0;
   out_8200145802550385466[43] = 0.0;
   out_8200145802550385466[44] = 0.0;
   out_8200145802550385466[45] = 0.0;
   out_8200145802550385466[46] = 0.0;
   out_8200145802550385466[47] = 0.0;
   out_8200145802550385466[48] = 0.0;
   out_8200145802550385466[49] = 0.0;
   out_8200145802550385466[50] = 0.0;
   out_8200145802550385466[51] = 0.0;
   out_8200145802550385466[52] = 0.0;
   out_8200145802550385466[53] = 0.0;
   out_8200145802550385466[54] = 0.0;
   out_8200145802550385466[55] = 0.0;
   out_8200145802550385466[56] = 0.0;
   out_8200145802550385466[57] = 1.0;
   out_8200145802550385466[58] = 0.0;
   out_8200145802550385466[59] = 0.0;
   out_8200145802550385466[60] = 0.0;
   out_8200145802550385466[61] = 0.0;
   out_8200145802550385466[62] = 0.0;
   out_8200145802550385466[63] = 0.0;
   out_8200145802550385466[64] = 0.0;
   out_8200145802550385466[65] = 0.0;
   out_8200145802550385466[66] = 0.0;
   out_8200145802550385466[67] = 0.0;
   out_8200145802550385466[68] = 0.0;
   out_8200145802550385466[69] = 0.0;
   out_8200145802550385466[70] = 0.0;
   out_8200145802550385466[71] = 0.0;
   out_8200145802550385466[72] = 0.0;
   out_8200145802550385466[73] = 0.0;
   out_8200145802550385466[74] = 0.0;
   out_8200145802550385466[75] = 0.0;
   out_8200145802550385466[76] = 1.0;
   out_8200145802550385466[77] = 0.0;
   out_8200145802550385466[78] = 0.0;
   out_8200145802550385466[79] = 0.0;
   out_8200145802550385466[80] = 0.0;
   out_8200145802550385466[81] = 0.0;
   out_8200145802550385466[82] = 0.0;
   out_8200145802550385466[83] = 0.0;
   out_8200145802550385466[84] = 0.0;
   out_8200145802550385466[85] = 0.0;
   out_8200145802550385466[86] = 0.0;
   out_8200145802550385466[87] = 0.0;
   out_8200145802550385466[88] = 0.0;
   out_8200145802550385466[89] = 0.0;
   out_8200145802550385466[90] = 0.0;
   out_8200145802550385466[91] = 0.0;
   out_8200145802550385466[92] = 0.0;
   out_8200145802550385466[93] = 0.0;
   out_8200145802550385466[94] = 0.0;
   out_8200145802550385466[95] = 1.0;
   out_8200145802550385466[96] = 0.0;
   out_8200145802550385466[97] = 0.0;
   out_8200145802550385466[98] = 0.0;
   out_8200145802550385466[99] = 0.0;
   out_8200145802550385466[100] = 0.0;
   out_8200145802550385466[101] = 0.0;
   out_8200145802550385466[102] = 0.0;
   out_8200145802550385466[103] = 0.0;
   out_8200145802550385466[104] = 0.0;
   out_8200145802550385466[105] = 0.0;
   out_8200145802550385466[106] = 0.0;
   out_8200145802550385466[107] = 0.0;
   out_8200145802550385466[108] = 0.0;
   out_8200145802550385466[109] = 0.0;
   out_8200145802550385466[110] = 0.0;
   out_8200145802550385466[111] = 0.0;
   out_8200145802550385466[112] = 0.0;
   out_8200145802550385466[113] = 0.0;
   out_8200145802550385466[114] = 1.0;
   out_8200145802550385466[115] = 0.0;
   out_8200145802550385466[116] = 0.0;
   out_8200145802550385466[117] = 0.0;
   out_8200145802550385466[118] = 0.0;
   out_8200145802550385466[119] = 0.0;
   out_8200145802550385466[120] = 0.0;
   out_8200145802550385466[121] = 0.0;
   out_8200145802550385466[122] = 0.0;
   out_8200145802550385466[123] = 0.0;
   out_8200145802550385466[124] = 0.0;
   out_8200145802550385466[125] = 0.0;
   out_8200145802550385466[126] = 0.0;
   out_8200145802550385466[127] = 0.0;
   out_8200145802550385466[128] = 0.0;
   out_8200145802550385466[129] = 0.0;
   out_8200145802550385466[130] = 0.0;
   out_8200145802550385466[131] = 0.0;
   out_8200145802550385466[132] = 0.0;
   out_8200145802550385466[133] = 1.0;
   out_8200145802550385466[134] = 0.0;
   out_8200145802550385466[135] = 0.0;
   out_8200145802550385466[136] = 0.0;
   out_8200145802550385466[137] = 0.0;
   out_8200145802550385466[138] = 0.0;
   out_8200145802550385466[139] = 0.0;
   out_8200145802550385466[140] = 0.0;
   out_8200145802550385466[141] = 0.0;
   out_8200145802550385466[142] = 0.0;
   out_8200145802550385466[143] = 0.0;
   out_8200145802550385466[144] = 0.0;
   out_8200145802550385466[145] = 0.0;
   out_8200145802550385466[146] = 0.0;
   out_8200145802550385466[147] = 0.0;
   out_8200145802550385466[148] = 0.0;
   out_8200145802550385466[149] = 0.0;
   out_8200145802550385466[150] = 0.0;
   out_8200145802550385466[151] = 0.0;
   out_8200145802550385466[152] = 1.0;
   out_8200145802550385466[153] = 0.0;
   out_8200145802550385466[154] = 0.0;
   out_8200145802550385466[155] = 0.0;
   out_8200145802550385466[156] = 0.0;
   out_8200145802550385466[157] = 0.0;
   out_8200145802550385466[158] = 0.0;
   out_8200145802550385466[159] = 0.0;
   out_8200145802550385466[160] = 0.0;
   out_8200145802550385466[161] = 0.0;
   out_8200145802550385466[162] = 0.0;
   out_8200145802550385466[163] = 0.0;
   out_8200145802550385466[164] = 0.0;
   out_8200145802550385466[165] = 0.0;
   out_8200145802550385466[166] = 0.0;
   out_8200145802550385466[167] = 0.0;
   out_8200145802550385466[168] = 0.0;
   out_8200145802550385466[169] = 0.0;
   out_8200145802550385466[170] = 0.0;
   out_8200145802550385466[171] = 1.0;
   out_8200145802550385466[172] = 0.0;
   out_8200145802550385466[173] = 0.0;
   out_8200145802550385466[174] = 0.0;
   out_8200145802550385466[175] = 0.0;
   out_8200145802550385466[176] = 0.0;
   out_8200145802550385466[177] = 0.0;
   out_8200145802550385466[178] = 0.0;
   out_8200145802550385466[179] = 0.0;
   out_8200145802550385466[180] = 0.0;
   out_8200145802550385466[181] = 0.0;
   out_8200145802550385466[182] = 0.0;
   out_8200145802550385466[183] = 0.0;
   out_8200145802550385466[184] = 0.0;
   out_8200145802550385466[185] = 0.0;
   out_8200145802550385466[186] = 0.0;
   out_8200145802550385466[187] = 0.0;
   out_8200145802550385466[188] = 0.0;
   out_8200145802550385466[189] = 0.0;
   out_8200145802550385466[190] = 1.0;
   out_8200145802550385466[191] = 0.0;
   out_8200145802550385466[192] = 0.0;
   out_8200145802550385466[193] = 0.0;
   out_8200145802550385466[194] = 0.0;
   out_8200145802550385466[195] = 0.0;
   out_8200145802550385466[196] = 0.0;
   out_8200145802550385466[197] = 0.0;
   out_8200145802550385466[198] = 0.0;
   out_8200145802550385466[199] = 0.0;
   out_8200145802550385466[200] = 0.0;
   out_8200145802550385466[201] = 0.0;
   out_8200145802550385466[202] = 0.0;
   out_8200145802550385466[203] = 0.0;
   out_8200145802550385466[204] = 0.0;
   out_8200145802550385466[205] = 0.0;
   out_8200145802550385466[206] = 0.0;
   out_8200145802550385466[207] = 0.0;
   out_8200145802550385466[208] = 0.0;
   out_8200145802550385466[209] = 1.0;
   out_8200145802550385466[210] = 0.0;
   out_8200145802550385466[211] = 0.0;
   out_8200145802550385466[212] = 0.0;
   out_8200145802550385466[213] = 0.0;
   out_8200145802550385466[214] = 0.0;
   out_8200145802550385466[215] = 0.0;
   out_8200145802550385466[216] = 0.0;
   out_8200145802550385466[217] = 0.0;
   out_8200145802550385466[218] = 0.0;
   out_8200145802550385466[219] = 0.0;
   out_8200145802550385466[220] = 0.0;
   out_8200145802550385466[221] = 0.0;
   out_8200145802550385466[222] = 0.0;
   out_8200145802550385466[223] = 0.0;
   out_8200145802550385466[224] = 0.0;
   out_8200145802550385466[225] = 0.0;
   out_8200145802550385466[226] = 0.0;
   out_8200145802550385466[227] = 0.0;
   out_8200145802550385466[228] = 1.0;
   out_8200145802550385466[229] = 0.0;
   out_8200145802550385466[230] = 0.0;
   out_8200145802550385466[231] = 0.0;
   out_8200145802550385466[232] = 0.0;
   out_8200145802550385466[233] = 0.0;
   out_8200145802550385466[234] = 0.0;
   out_8200145802550385466[235] = 0.0;
   out_8200145802550385466[236] = 0.0;
   out_8200145802550385466[237] = 0.0;
   out_8200145802550385466[238] = 0.0;
   out_8200145802550385466[239] = 0.0;
   out_8200145802550385466[240] = 0.0;
   out_8200145802550385466[241] = 0.0;
   out_8200145802550385466[242] = 0.0;
   out_8200145802550385466[243] = 0.0;
   out_8200145802550385466[244] = 0.0;
   out_8200145802550385466[245] = 0.0;
   out_8200145802550385466[246] = 0.0;
   out_8200145802550385466[247] = 1.0;
   out_8200145802550385466[248] = 0.0;
   out_8200145802550385466[249] = 0.0;
   out_8200145802550385466[250] = 0.0;
   out_8200145802550385466[251] = 0.0;
   out_8200145802550385466[252] = 0.0;
   out_8200145802550385466[253] = 0.0;
   out_8200145802550385466[254] = 0.0;
   out_8200145802550385466[255] = 0.0;
   out_8200145802550385466[256] = 0.0;
   out_8200145802550385466[257] = 0.0;
   out_8200145802550385466[258] = 0.0;
   out_8200145802550385466[259] = 0.0;
   out_8200145802550385466[260] = 0.0;
   out_8200145802550385466[261] = 0.0;
   out_8200145802550385466[262] = 0.0;
   out_8200145802550385466[263] = 0.0;
   out_8200145802550385466[264] = 0.0;
   out_8200145802550385466[265] = 0.0;
   out_8200145802550385466[266] = 1.0;
   out_8200145802550385466[267] = 0.0;
   out_8200145802550385466[268] = 0.0;
   out_8200145802550385466[269] = 0.0;
   out_8200145802550385466[270] = 0.0;
   out_8200145802550385466[271] = 0.0;
   out_8200145802550385466[272] = 0.0;
   out_8200145802550385466[273] = 0.0;
   out_8200145802550385466[274] = 0.0;
   out_8200145802550385466[275] = 0.0;
   out_8200145802550385466[276] = 0.0;
   out_8200145802550385466[277] = 0.0;
   out_8200145802550385466[278] = 0.0;
   out_8200145802550385466[279] = 0.0;
   out_8200145802550385466[280] = 0.0;
   out_8200145802550385466[281] = 0.0;
   out_8200145802550385466[282] = 0.0;
   out_8200145802550385466[283] = 0.0;
   out_8200145802550385466[284] = 0.0;
   out_8200145802550385466[285] = 1.0;
   out_8200145802550385466[286] = 0.0;
   out_8200145802550385466[287] = 0.0;
   out_8200145802550385466[288] = 0.0;
   out_8200145802550385466[289] = 0.0;
   out_8200145802550385466[290] = 0.0;
   out_8200145802550385466[291] = 0.0;
   out_8200145802550385466[292] = 0.0;
   out_8200145802550385466[293] = 0.0;
   out_8200145802550385466[294] = 0.0;
   out_8200145802550385466[295] = 0.0;
   out_8200145802550385466[296] = 0.0;
   out_8200145802550385466[297] = 0.0;
   out_8200145802550385466[298] = 0.0;
   out_8200145802550385466[299] = 0.0;
   out_8200145802550385466[300] = 0.0;
   out_8200145802550385466[301] = 0.0;
   out_8200145802550385466[302] = 0.0;
   out_8200145802550385466[303] = 0.0;
   out_8200145802550385466[304] = 1.0;
   out_8200145802550385466[305] = 0.0;
   out_8200145802550385466[306] = 0.0;
   out_8200145802550385466[307] = 0.0;
   out_8200145802550385466[308] = 0.0;
   out_8200145802550385466[309] = 0.0;
   out_8200145802550385466[310] = 0.0;
   out_8200145802550385466[311] = 0.0;
   out_8200145802550385466[312] = 0.0;
   out_8200145802550385466[313] = 0.0;
   out_8200145802550385466[314] = 0.0;
   out_8200145802550385466[315] = 0.0;
   out_8200145802550385466[316] = 0.0;
   out_8200145802550385466[317] = 0.0;
   out_8200145802550385466[318] = 0.0;
   out_8200145802550385466[319] = 0.0;
   out_8200145802550385466[320] = 0.0;
   out_8200145802550385466[321] = 0.0;
   out_8200145802550385466[322] = 0.0;
   out_8200145802550385466[323] = 1.0;
}
void f_fun(double *state, double dt, double *out_3154493756264028272) {
   out_3154493756264028272[0] = atan2((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), -(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]));
   out_3154493756264028272[1] = asin(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]));
   out_3154493756264028272[2] = atan2(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), -(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]));
   out_3154493756264028272[3] = dt*state[12] + state[3];
   out_3154493756264028272[4] = dt*state[13] + state[4];
   out_3154493756264028272[5] = dt*state[14] + state[5];
   out_3154493756264028272[6] = state[6];
   out_3154493756264028272[7] = state[7];
   out_3154493756264028272[8] = state[8];
   out_3154493756264028272[9] = state[9];
   out_3154493756264028272[10] = state[10];
   out_3154493756264028272[11] = state[11];
   out_3154493756264028272[12] = state[12];
   out_3154493756264028272[13] = state[13];
   out_3154493756264028272[14] = state[14];
   out_3154493756264028272[15] = state[15];
   out_3154493756264028272[16] = state[16];
   out_3154493756264028272[17] = state[17];
}
void F_fun(double *state, double dt, double *out_3844222318897373612) {
   out_3844222318897373612[0] = ((-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*cos(state[0])*cos(state[1]) - sin(state[0])*cos(dt*state[6])*cos(dt*state[7])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + ((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*cos(state[0])*cos(state[1]) - sin(dt*state[6])*sin(state[0])*cos(dt*state[7])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_3844222318897373612[1] = ((-sin(dt*state[6])*sin(dt*state[8]) - sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*cos(state[1]) - (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*sin(state[1]) - sin(state[1])*cos(dt*state[6])*cos(dt*state[7])*cos(state[0]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*sin(state[1]) + (-sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) + sin(dt*state[8])*cos(dt*state[6]))*cos(state[1]) - sin(dt*state[6])*sin(state[1])*cos(dt*state[7])*cos(state[0]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_3844222318897373612[2] = 0;
   out_3844222318897373612[3] = 0;
   out_3844222318897373612[4] = 0;
   out_3844222318897373612[5] = 0;
   out_3844222318897373612[6] = (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(dt*cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*sin(dt*state[8]) - dt*sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-dt*sin(dt*state[6])*cos(dt*state[8]) + dt*sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) - dt*cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (dt*sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_3844222318897373612[7] = (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[6])*sin(dt*state[7])*cos(state[0])*cos(state[1]) + dt*sin(dt*state[6])*sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) - dt*sin(dt*state[6])*sin(state[1])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[7])*cos(dt*state[6])*cos(state[0])*cos(state[1]) + dt*sin(dt*state[8])*sin(state[0])*cos(dt*state[6])*cos(dt*state[7])*cos(state[1]) - dt*sin(state[1])*cos(dt*state[6])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_3844222318897373612[8] = ((dt*sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + dt*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (dt*sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + ((dt*sin(dt*state[6])*sin(dt*state[8]) + dt*sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*cos(dt*state[8]) + dt*sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_3844222318897373612[9] = 0;
   out_3844222318897373612[10] = 0;
   out_3844222318897373612[11] = 0;
   out_3844222318897373612[12] = 0;
   out_3844222318897373612[13] = 0;
   out_3844222318897373612[14] = 0;
   out_3844222318897373612[15] = 0;
   out_3844222318897373612[16] = 0;
   out_3844222318897373612[17] = 0;
   out_3844222318897373612[18] = (-sin(dt*state[7])*sin(state[0])*cos(state[1]) - sin(dt*state[8])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_3844222318897373612[19] = (-sin(dt*state[7])*sin(state[1])*cos(state[0]) + sin(dt*state[8])*sin(state[0])*sin(state[1])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_3844222318897373612[20] = 0;
   out_3844222318897373612[21] = 0;
   out_3844222318897373612[22] = 0;
   out_3844222318897373612[23] = 0;
   out_3844222318897373612[24] = 0;
   out_3844222318897373612[25] = (dt*sin(dt*state[7])*sin(dt*state[8])*sin(state[0])*cos(state[1]) - dt*sin(dt*state[7])*sin(state[1])*cos(dt*state[8]) + dt*cos(dt*state[7])*cos(state[0])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_3844222318897373612[26] = (-dt*sin(dt*state[8])*sin(state[1])*cos(dt*state[7]) - dt*sin(state[0])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_3844222318897373612[27] = 0;
   out_3844222318897373612[28] = 0;
   out_3844222318897373612[29] = 0;
   out_3844222318897373612[30] = 0;
   out_3844222318897373612[31] = 0;
   out_3844222318897373612[32] = 0;
   out_3844222318897373612[33] = 0;
   out_3844222318897373612[34] = 0;
   out_3844222318897373612[35] = 0;
   out_3844222318897373612[36] = ((sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[7]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[7]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_3844222318897373612[37] = (-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(-sin(dt*state[7])*sin(state[2])*cos(state[0])*cos(state[1]) + sin(dt*state[8])*sin(state[0])*sin(state[2])*cos(dt*state[7])*cos(state[1]) - sin(state[1])*sin(state[2])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*(-sin(dt*state[7])*cos(state[0])*cos(state[1])*cos(state[2]) + sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1])*cos(state[2]) - sin(state[1])*cos(dt*state[7])*cos(dt*state[8])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_3844222318897373612[38] = ((-sin(state[0])*sin(state[2]) - sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (-sin(state[0])*sin(state[1])*sin(state[2]) - cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_3844222318897373612[39] = 0;
   out_3844222318897373612[40] = 0;
   out_3844222318897373612[41] = 0;
   out_3844222318897373612[42] = 0;
   out_3844222318897373612[43] = (-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(dt*(sin(state[0])*cos(state[2]) - sin(state[1])*sin(state[2])*cos(state[0]))*cos(dt*state[7]) - dt*(sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[7])*sin(dt*state[8]) - dt*sin(dt*state[7])*sin(state[2])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*(dt*(-sin(state[0])*sin(state[2]) - sin(state[1])*cos(state[0])*cos(state[2]))*cos(dt*state[7]) - dt*(sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[7])*sin(dt*state[8]) - dt*sin(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_3844222318897373612[44] = (dt*(sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*cos(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*sin(state[2])*cos(dt*state[7])*cos(state[1]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + (dt*(sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*cos(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[7])*cos(state[1])*cos(state[2]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_3844222318897373612[45] = 0;
   out_3844222318897373612[46] = 0;
   out_3844222318897373612[47] = 0;
   out_3844222318897373612[48] = 0;
   out_3844222318897373612[49] = 0;
   out_3844222318897373612[50] = 0;
   out_3844222318897373612[51] = 0;
   out_3844222318897373612[52] = 0;
   out_3844222318897373612[53] = 0;
   out_3844222318897373612[54] = 0;
   out_3844222318897373612[55] = 0;
   out_3844222318897373612[56] = 0;
   out_3844222318897373612[57] = 1;
   out_3844222318897373612[58] = 0;
   out_3844222318897373612[59] = 0;
   out_3844222318897373612[60] = 0;
   out_3844222318897373612[61] = 0;
   out_3844222318897373612[62] = 0;
   out_3844222318897373612[63] = 0;
   out_3844222318897373612[64] = 0;
   out_3844222318897373612[65] = 0;
   out_3844222318897373612[66] = dt;
   out_3844222318897373612[67] = 0;
   out_3844222318897373612[68] = 0;
   out_3844222318897373612[69] = 0;
   out_3844222318897373612[70] = 0;
   out_3844222318897373612[71] = 0;
   out_3844222318897373612[72] = 0;
   out_3844222318897373612[73] = 0;
   out_3844222318897373612[74] = 0;
   out_3844222318897373612[75] = 0;
   out_3844222318897373612[76] = 1;
   out_3844222318897373612[77] = 0;
   out_3844222318897373612[78] = 0;
   out_3844222318897373612[79] = 0;
   out_3844222318897373612[80] = 0;
   out_3844222318897373612[81] = 0;
   out_3844222318897373612[82] = 0;
   out_3844222318897373612[83] = 0;
   out_3844222318897373612[84] = 0;
   out_3844222318897373612[85] = dt;
   out_3844222318897373612[86] = 0;
   out_3844222318897373612[87] = 0;
   out_3844222318897373612[88] = 0;
   out_3844222318897373612[89] = 0;
   out_3844222318897373612[90] = 0;
   out_3844222318897373612[91] = 0;
   out_3844222318897373612[92] = 0;
   out_3844222318897373612[93] = 0;
   out_3844222318897373612[94] = 0;
   out_3844222318897373612[95] = 1;
   out_3844222318897373612[96] = 0;
   out_3844222318897373612[97] = 0;
   out_3844222318897373612[98] = 0;
   out_3844222318897373612[99] = 0;
   out_3844222318897373612[100] = 0;
   out_3844222318897373612[101] = 0;
   out_3844222318897373612[102] = 0;
   out_3844222318897373612[103] = 0;
   out_3844222318897373612[104] = dt;
   out_3844222318897373612[105] = 0;
   out_3844222318897373612[106] = 0;
   out_3844222318897373612[107] = 0;
   out_3844222318897373612[108] = 0;
   out_3844222318897373612[109] = 0;
   out_3844222318897373612[110] = 0;
   out_3844222318897373612[111] = 0;
   out_3844222318897373612[112] = 0;
   out_3844222318897373612[113] = 0;
   out_3844222318897373612[114] = 1;
   out_3844222318897373612[115] = 0;
   out_3844222318897373612[116] = 0;
   out_3844222318897373612[117] = 0;
   out_3844222318897373612[118] = 0;
   out_3844222318897373612[119] = 0;
   out_3844222318897373612[120] = 0;
   out_3844222318897373612[121] = 0;
   out_3844222318897373612[122] = 0;
   out_3844222318897373612[123] = 0;
   out_3844222318897373612[124] = 0;
   out_3844222318897373612[125] = 0;
   out_3844222318897373612[126] = 0;
   out_3844222318897373612[127] = 0;
   out_3844222318897373612[128] = 0;
   out_3844222318897373612[129] = 0;
   out_3844222318897373612[130] = 0;
   out_3844222318897373612[131] = 0;
   out_3844222318897373612[132] = 0;
   out_3844222318897373612[133] = 1;
   out_3844222318897373612[134] = 0;
   out_3844222318897373612[135] = 0;
   out_3844222318897373612[136] = 0;
   out_3844222318897373612[137] = 0;
   out_3844222318897373612[138] = 0;
   out_3844222318897373612[139] = 0;
   out_3844222318897373612[140] = 0;
   out_3844222318897373612[141] = 0;
   out_3844222318897373612[142] = 0;
   out_3844222318897373612[143] = 0;
   out_3844222318897373612[144] = 0;
   out_3844222318897373612[145] = 0;
   out_3844222318897373612[146] = 0;
   out_3844222318897373612[147] = 0;
   out_3844222318897373612[148] = 0;
   out_3844222318897373612[149] = 0;
   out_3844222318897373612[150] = 0;
   out_3844222318897373612[151] = 0;
   out_3844222318897373612[152] = 1;
   out_3844222318897373612[153] = 0;
   out_3844222318897373612[154] = 0;
   out_3844222318897373612[155] = 0;
   out_3844222318897373612[156] = 0;
   out_3844222318897373612[157] = 0;
   out_3844222318897373612[158] = 0;
   out_3844222318897373612[159] = 0;
   out_3844222318897373612[160] = 0;
   out_3844222318897373612[161] = 0;
   out_3844222318897373612[162] = 0;
   out_3844222318897373612[163] = 0;
   out_3844222318897373612[164] = 0;
   out_3844222318897373612[165] = 0;
   out_3844222318897373612[166] = 0;
   out_3844222318897373612[167] = 0;
   out_3844222318897373612[168] = 0;
   out_3844222318897373612[169] = 0;
   out_3844222318897373612[170] = 0;
   out_3844222318897373612[171] = 1;
   out_3844222318897373612[172] = 0;
   out_3844222318897373612[173] = 0;
   out_3844222318897373612[174] = 0;
   out_3844222318897373612[175] = 0;
   out_3844222318897373612[176] = 0;
   out_3844222318897373612[177] = 0;
   out_3844222318897373612[178] = 0;
   out_3844222318897373612[179] = 0;
   out_3844222318897373612[180] = 0;
   out_3844222318897373612[181] = 0;
   out_3844222318897373612[182] = 0;
   out_3844222318897373612[183] = 0;
   out_3844222318897373612[184] = 0;
   out_3844222318897373612[185] = 0;
   out_3844222318897373612[186] = 0;
   out_3844222318897373612[187] = 0;
   out_3844222318897373612[188] = 0;
   out_3844222318897373612[189] = 0;
   out_3844222318897373612[190] = 1;
   out_3844222318897373612[191] = 0;
   out_3844222318897373612[192] = 0;
   out_3844222318897373612[193] = 0;
   out_3844222318897373612[194] = 0;
   out_3844222318897373612[195] = 0;
   out_3844222318897373612[196] = 0;
   out_3844222318897373612[197] = 0;
   out_3844222318897373612[198] = 0;
   out_3844222318897373612[199] = 0;
   out_3844222318897373612[200] = 0;
   out_3844222318897373612[201] = 0;
   out_3844222318897373612[202] = 0;
   out_3844222318897373612[203] = 0;
   out_3844222318897373612[204] = 0;
   out_3844222318897373612[205] = 0;
   out_3844222318897373612[206] = 0;
   out_3844222318897373612[207] = 0;
   out_3844222318897373612[208] = 0;
   out_3844222318897373612[209] = 1;
   out_3844222318897373612[210] = 0;
   out_3844222318897373612[211] = 0;
   out_3844222318897373612[212] = 0;
   out_3844222318897373612[213] = 0;
   out_3844222318897373612[214] = 0;
   out_3844222318897373612[215] = 0;
   out_3844222318897373612[216] = 0;
   out_3844222318897373612[217] = 0;
   out_3844222318897373612[218] = 0;
   out_3844222318897373612[219] = 0;
   out_3844222318897373612[220] = 0;
   out_3844222318897373612[221] = 0;
   out_3844222318897373612[222] = 0;
   out_3844222318897373612[223] = 0;
   out_3844222318897373612[224] = 0;
   out_3844222318897373612[225] = 0;
   out_3844222318897373612[226] = 0;
   out_3844222318897373612[227] = 0;
   out_3844222318897373612[228] = 1;
   out_3844222318897373612[229] = 0;
   out_3844222318897373612[230] = 0;
   out_3844222318897373612[231] = 0;
   out_3844222318897373612[232] = 0;
   out_3844222318897373612[233] = 0;
   out_3844222318897373612[234] = 0;
   out_3844222318897373612[235] = 0;
   out_3844222318897373612[236] = 0;
   out_3844222318897373612[237] = 0;
   out_3844222318897373612[238] = 0;
   out_3844222318897373612[239] = 0;
   out_3844222318897373612[240] = 0;
   out_3844222318897373612[241] = 0;
   out_3844222318897373612[242] = 0;
   out_3844222318897373612[243] = 0;
   out_3844222318897373612[244] = 0;
   out_3844222318897373612[245] = 0;
   out_3844222318897373612[246] = 0;
   out_3844222318897373612[247] = 1;
   out_3844222318897373612[248] = 0;
   out_3844222318897373612[249] = 0;
   out_3844222318897373612[250] = 0;
   out_3844222318897373612[251] = 0;
   out_3844222318897373612[252] = 0;
   out_3844222318897373612[253] = 0;
   out_3844222318897373612[254] = 0;
   out_3844222318897373612[255] = 0;
   out_3844222318897373612[256] = 0;
   out_3844222318897373612[257] = 0;
   out_3844222318897373612[258] = 0;
   out_3844222318897373612[259] = 0;
   out_3844222318897373612[260] = 0;
   out_3844222318897373612[261] = 0;
   out_3844222318897373612[262] = 0;
   out_3844222318897373612[263] = 0;
   out_3844222318897373612[264] = 0;
   out_3844222318897373612[265] = 0;
   out_3844222318897373612[266] = 1;
   out_3844222318897373612[267] = 0;
   out_3844222318897373612[268] = 0;
   out_3844222318897373612[269] = 0;
   out_3844222318897373612[270] = 0;
   out_3844222318897373612[271] = 0;
   out_3844222318897373612[272] = 0;
   out_3844222318897373612[273] = 0;
   out_3844222318897373612[274] = 0;
   out_3844222318897373612[275] = 0;
   out_3844222318897373612[276] = 0;
   out_3844222318897373612[277] = 0;
   out_3844222318897373612[278] = 0;
   out_3844222318897373612[279] = 0;
   out_3844222318897373612[280] = 0;
   out_3844222318897373612[281] = 0;
   out_3844222318897373612[282] = 0;
   out_3844222318897373612[283] = 0;
   out_3844222318897373612[284] = 0;
   out_3844222318897373612[285] = 1;
   out_3844222318897373612[286] = 0;
   out_3844222318897373612[287] = 0;
   out_3844222318897373612[288] = 0;
   out_3844222318897373612[289] = 0;
   out_3844222318897373612[290] = 0;
   out_3844222318897373612[291] = 0;
   out_3844222318897373612[292] = 0;
   out_3844222318897373612[293] = 0;
   out_3844222318897373612[294] = 0;
   out_3844222318897373612[295] = 0;
   out_3844222318897373612[296] = 0;
   out_3844222318897373612[297] = 0;
   out_3844222318897373612[298] = 0;
   out_3844222318897373612[299] = 0;
   out_3844222318897373612[300] = 0;
   out_3844222318897373612[301] = 0;
   out_3844222318897373612[302] = 0;
   out_3844222318897373612[303] = 0;
   out_3844222318897373612[304] = 1;
   out_3844222318897373612[305] = 0;
   out_3844222318897373612[306] = 0;
   out_3844222318897373612[307] = 0;
   out_3844222318897373612[308] = 0;
   out_3844222318897373612[309] = 0;
   out_3844222318897373612[310] = 0;
   out_3844222318897373612[311] = 0;
   out_3844222318897373612[312] = 0;
   out_3844222318897373612[313] = 0;
   out_3844222318897373612[314] = 0;
   out_3844222318897373612[315] = 0;
   out_3844222318897373612[316] = 0;
   out_3844222318897373612[317] = 0;
   out_3844222318897373612[318] = 0;
   out_3844222318897373612[319] = 0;
   out_3844222318897373612[320] = 0;
   out_3844222318897373612[321] = 0;
   out_3844222318897373612[322] = 0;
   out_3844222318897373612[323] = 1;
}
void h_4(double *state, double *unused, double *out_7417392044831538702) {
   out_7417392044831538702[0] = state[6] + state[9];
   out_7417392044831538702[1] = state[7] + state[10];
   out_7417392044831538702[2] = state[8] + state[11];
}
void H_4(double *state, double *unused, double *out_744215863507435876) {
   out_744215863507435876[0] = 0;
   out_744215863507435876[1] = 0;
   out_744215863507435876[2] = 0;
   out_744215863507435876[3] = 0;
   out_744215863507435876[4] = 0;
   out_744215863507435876[5] = 0;
   out_744215863507435876[6] = 1;
   out_744215863507435876[7] = 0;
   out_744215863507435876[8] = 0;
   out_744215863507435876[9] = 1;
   out_744215863507435876[10] = 0;
   out_744215863507435876[11] = 0;
   out_744215863507435876[12] = 0;
   out_744215863507435876[13] = 0;
   out_744215863507435876[14] = 0;
   out_744215863507435876[15] = 0;
   out_744215863507435876[16] = 0;
   out_744215863507435876[17] = 0;
   out_744215863507435876[18] = 0;
   out_744215863507435876[19] = 0;
   out_744215863507435876[20] = 0;
   out_744215863507435876[21] = 0;
   out_744215863507435876[22] = 0;
   out_744215863507435876[23] = 0;
   out_744215863507435876[24] = 0;
   out_744215863507435876[25] = 1;
   out_744215863507435876[26] = 0;
   out_744215863507435876[27] = 0;
   out_744215863507435876[28] = 1;
   out_744215863507435876[29] = 0;
   out_744215863507435876[30] = 0;
   out_744215863507435876[31] = 0;
   out_744215863507435876[32] = 0;
   out_744215863507435876[33] = 0;
   out_744215863507435876[34] = 0;
   out_744215863507435876[35] = 0;
   out_744215863507435876[36] = 0;
   out_744215863507435876[37] = 0;
   out_744215863507435876[38] = 0;
   out_744215863507435876[39] = 0;
   out_744215863507435876[40] = 0;
   out_744215863507435876[41] = 0;
   out_744215863507435876[42] = 0;
   out_744215863507435876[43] = 0;
   out_744215863507435876[44] = 1;
   out_744215863507435876[45] = 0;
   out_744215863507435876[46] = 0;
   out_744215863507435876[47] = 1;
   out_744215863507435876[48] = 0;
   out_744215863507435876[49] = 0;
   out_744215863507435876[50] = 0;
   out_744215863507435876[51] = 0;
   out_744215863507435876[52] = 0;
   out_744215863507435876[53] = 0;
}
void h_10(double *state, double *unused, double *out_5837768205443090035) {
   out_5837768205443090035[0] = 9.8100000000000005*sin(state[1]) - state[4]*state[8] + state[5]*state[7] + state[12] + state[15];
   out_5837768205443090035[1] = -9.8100000000000005*sin(state[0])*cos(state[1]) + state[3]*state[8] - state[5]*state[6] + state[13] + state[16];
   out_5837768205443090035[2] = -9.8100000000000005*cos(state[0])*cos(state[1]) - state[3]*state[7] + state[4]*state[6] + state[14] + state[17];
}
void H_10(double *state, double *unused, double *out_6045792490383943628) {
   out_6045792490383943628[0] = 0;
   out_6045792490383943628[1] = 9.8100000000000005*cos(state[1]);
   out_6045792490383943628[2] = 0;
   out_6045792490383943628[3] = 0;
   out_6045792490383943628[4] = -state[8];
   out_6045792490383943628[5] = state[7];
   out_6045792490383943628[6] = 0;
   out_6045792490383943628[7] = state[5];
   out_6045792490383943628[8] = -state[4];
   out_6045792490383943628[9] = 0;
   out_6045792490383943628[10] = 0;
   out_6045792490383943628[11] = 0;
   out_6045792490383943628[12] = 1;
   out_6045792490383943628[13] = 0;
   out_6045792490383943628[14] = 0;
   out_6045792490383943628[15] = 1;
   out_6045792490383943628[16] = 0;
   out_6045792490383943628[17] = 0;
   out_6045792490383943628[18] = -9.8100000000000005*cos(state[0])*cos(state[1]);
   out_6045792490383943628[19] = 9.8100000000000005*sin(state[0])*sin(state[1]);
   out_6045792490383943628[20] = 0;
   out_6045792490383943628[21] = state[8];
   out_6045792490383943628[22] = 0;
   out_6045792490383943628[23] = -state[6];
   out_6045792490383943628[24] = -state[5];
   out_6045792490383943628[25] = 0;
   out_6045792490383943628[26] = state[3];
   out_6045792490383943628[27] = 0;
   out_6045792490383943628[28] = 0;
   out_6045792490383943628[29] = 0;
   out_6045792490383943628[30] = 0;
   out_6045792490383943628[31] = 1;
   out_6045792490383943628[32] = 0;
   out_6045792490383943628[33] = 0;
   out_6045792490383943628[34] = 1;
   out_6045792490383943628[35] = 0;
   out_6045792490383943628[36] = 9.8100000000000005*sin(state[0])*cos(state[1]);
   out_6045792490383943628[37] = 9.8100000000000005*sin(state[1])*cos(state[0]);
   out_6045792490383943628[38] = 0;
   out_6045792490383943628[39] = -state[7];
   out_6045792490383943628[40] = state[6];
   out_6045792490383943628[41] = 0;
   out_6045792490383943628[42] = state[4];
   out_6045792490383943628[43] = -state[3];
   out_6045792490383943628[44] = 0;
   out_6045792490383943628[45] = 0;
   out_6045792490383943628[46] = 0;
   out_6045792490383943628[47] = 0;
   out_6045792490383943628[48] = 0;
   out_6045792490383943628[49] = 0;
   out_6045792490383943628[50] = 1;
   out_6045792490383943628[51] = 0;
   out_6045792490383943628[52] = 0;
   out_6045792490383943628[53] = 1;
}
void h_13(double *state, double *unused, double *out_886522868392701902) {
   out_886522868392701902[0] = state[3];
   out_886522868392701902[1] = state[4];
   out_886522868392701902[2] = state[5];
}
void H_13(double *state, double *unused, double *out_2468057961824896925) {
   out_2468057961824896925[0] = 0;
   out_2468057961824896925[1] = 0;
   out_2468057961824896925[2] = 0;
   out_2468057961824896925[3] = 1;
   out_2468057961824896925[4] = 0;
   out_2468057961824896925[5] = 0;
   out_2468057961824896925[6] = 0;
   out_2468057961824896925[7] = 0;
   out_2468057961824896925[8] = 0;
   out_2468057961824896925[9] = 0;
   out_2468057961824896925[10] = 0;
   out_2468057961824896925[11] = 0;
   out_2468057961824896925[12] = 0;
   out_2468057961824896925[13] = 0;
   out_2468057961824896925[14] = 0;
   out_2468057961824896925[15] = 0;
   out_2468057961824896925[16] = 0;
   out_2468057961824896925[17] = 0;
   out_2468057961824896925[18] = 0;
   out_2468057961824896925[19] = 0;
   out_2468057961824896925[20] = 0;
   out_2468057961824896925[21] = 0;
   out_2468057961824896925[22] = 1;
   out_2468057961824896925[23] = 0;
   out_2468057961824896925[24] = 0;
   out_2468057961824896925[25] = 0;
   out_2468057961824896925[26] = 0;
   out_2468057961824896925[27] = 0;
   out_2468057961824896925[28] = 0;
   out_2468057961824896925[29] = 0;
   out_2468057961824896925[30] = 0;
   out_2468057961824896925[31] = 0;
   out_2468057961824896925[32] = 0;
   out_2468057961824896925[33] = 0;
   out_2468057961824896925[34] = 0;
   out_2468057961824896925[35] = 0;
   out_2468057961824896925[36] = 0;
   out_2468057961824896925[37] = 0;
   out_2468057961824896925[38] = 0;
   out_2468057961824896925[39] = 0;
   out_2468057961824896925[40] = 0;
   out_2468057961824896925[41] = 1;
   out_2468057961824896925[42] = 0;
   out_2468057961824896925[43] = 0;
   out_2468057961824896925[44] = 0;
   out_2468057961824896925[45] = 0;
   out_2468057961824896925[46] = 0;
   out_2468057961824896925[47] = 0;
   out_2468057961824896925[48] = 0;
   out_2468057961824896925[49] = 0;
   out_2468057961824896925[50] = 0;
   out_2468057961824896925[51] = 0;
   out_2468057961824896925[52] = 0;
   out_2468057961824896925[53] = 0;
}
void h_14(double *state, double *unused, double *out_8921497272601995159) {
   out_8921497272601995159[0] = state[6];
   out_8921497272601995159[1] = state[7];
   out_8921497272601995159[2] = state[8];
}
void H_14(double *state, double *unused, double *out_8225361678787176300) {
   out_8225361678787176300[0] = 0;
   out_8225361678787176300[1] = 0;
   out_8225361678787176300[2] = 0;
   out_8225361678787176300[3] = 0;
   out_8225361678787176300[4] = 0;
   out_8225361678787176300[5] = 0;
   out_8225361678787176300[6] = 1;
   out_8225361678787176300[7] = 0;
   out_8225361678787176300[8] = 0;
   out_8225361678787176300[9] = 0;
   out_8225361678787176300[10] = 0;
   out_8225361678787176300[11] = 0;
   out_8225361678787176300[12] = 0;
   out_8225361678787176300[13] = 0;
   out_8225361678787176300[14] = 0;
   out_8225361678787176300[15] = 0;
   out_8225361678787176300[16] = 0;
   out_8225361678787176300[17] = 0;
   out_8225361678787176300[18] = 0;
   out_8225361678787176300[19] = 0;
   out_8225361678787176300[20] = 0;
   out_8225361678787176300[21] = 0;
   out_8225361678787176300[22] = 0;
   out_8225361678787176300[23] = 0;
   out_8225361678787176300[24] = 0;
   out_8225361678787176300[25] = 1;
   out_8225361678787176300[26] = 0;
   out_8225361678787176300[27] = 0;
   out_8225361678787176300[28] = 0;
   out_8225361678787176300[29] = 0;
   out_8225361678787176300[30] = 0;
   out_8225361678787176300[31] = 0;
   out_8225361678787176300[32] = 0;
   out_8225361678787176300[33] = 0;
   out_8225361678787176300[34] = 0;
   out_8225361678787176300[35] = 0;
   out_8225361678787176300[36] = 0;
   out_8225361678787176300[37] = 0;
   out_8225361678787176300[38] = 0;
   out_8225361678787176300[39] = 0;
   out_8225361678787176300[40] = 0;
   out_8225361678787176300[41] = 0;
   out_8225361678787176300[42] = 0;
   out_8225361678787176300[43] = 0;
   out_8225361678787176300[44] = 1;
   out_8225361678787176300[45] = 0;
   out_8225361678787176300[46] = 0;
   out_8225361678787176300[47] = 0;
   out_8225361678787176300[48] = 0;
   out_8225361678787176300[49] = 0;
   out_8225361678787176300[50] = 0;
   out_8225361678787176300[51] = 0;
   out_8225361678787176300[52] = 0;
   out_8225361678787176300[53] = 0;
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
void pose_err_fun(double *nom_x, double *delta_x, double *out_6609500045983475884) {
  err_fun(nom_x, delta_x, out_6609500045983475884);
}
void pose_inv_err_fun(double *nom_x, double *true_x, double *out_2251582086712269854) {
  inv_err_fun(nom_x, true_x, out_2251582086712269854);
}
void pose_H_mod_fun(double *state, double *out_8200145802550385466) {
  H_mod_fun(state, out_8200145802550385466);
}
void pose_f_fun(double *state, double dt, double *out_3154493756264028272) {
  f_fun(state,  dt, out_3154493756264028272);
}
void pose_F_fun(double *state, double dt, double *out_3844222318897373612) {
  F_fun(state,  dt, out_3844222318897373612);
}
void pose_h_4(double *state, double *unused, double *out_7417392044831538702) {
  h_4(state, unused, out_7417392044831538702);
}
void pose_H_4(double *state, double *unused, double *out_744215863507435876) {
  H_4(state, unused, out_744215863507435876);
}
void pose_h_10(double *state, double *unused, double *out_5837768205443090035) {
  h_10(state, unused, out_5837768205443090035);
}
void pose_H_10(double *state, double *unused, double *out_6045792490383943628) {
  H_10(state, unused, out_6045792490383943628);
}
void pose_h_13(double *state, double *unused, double *out_886522868392701902) {
  h_13(state, unused, out_886522868392701902);
}
void pose_H_13(double *state, double *unused, double *out_2468057961824896925) {
  H_13(state, unused, out_2468057961824896925);
}
void pose_h_14(double *state, double *unused, double *out_8921497272601995159) {
  h_14(state, unused, out_8921497272601995159);
}
void pose_H_14(double *state, double *unused, double *out_8225361678787176300) {
  H_14(state, unused, out_8225361678787176300);
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
