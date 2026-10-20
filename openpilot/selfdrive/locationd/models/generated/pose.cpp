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
void err_fun(double *nom_x, double *delta_x, double *out_6205306553489213410) {
   out_6205306553489213410[0] = delta_x[0] + nom_x[0];
   out_6205306553489213410[1] = delta_x[1] + nom_x[1];
   out_6205306553489213410[2] = delta_x[2] + nom_x[2];
   out_6205306553489213410[3] = delta_x[3] + nom_x[3];
   out_6205306553489213410[4] = delta_x[4] + nom_x[4];
   out_6205306553489213410[5] = delta_x[5] + nom_x[5];
   out_6205306553489213410[6] = delta_x[6] + nom_x[6];
   out_6205306553489213410[7] = delta_x[7] + nom_x[7];
   out_6205306553489213410[8] = delta_x[8] + nom_x[8];
   out_6205306553489213410[9] = delta_x[9] + nom_x[9];
   out_6205306553489213410[10] = delta_x[10] + nom_x[10];
   out_6205306553489213410[11] = delta_x[11] + nom_x[11];
   out_6205306553489213410[12] = delta_x[12] + nom_x[12];
   out_6205306553489213410[13] = delta_x[13] + nom_x[13];
   out_6205306553489213410[14] = delta_x[14] + nom_x[14];
   out_6205306553489213410[15] = delta_x[15] + nom_x[15];
   out_6205306553489213410[16] = delta_x[16] + nom_x[16];
   out_6205306553489213410[17] = delta_x[17] + nom_x[17];
}
void inv_err_fun(double *nom_x, double *true_x, double *out_1970164945047322285) {
   out_1970164945047322285[0] = -nom_x[0] + true_x[0];
   out_1970164945047322285[1] = -nom_x[1] + true_x[1];
   out_1970164945047322285[2] = -nom_x[2] + true_x[2];
   out_1970164945047322285[3] = -nom_x[3] + true_x[3];
   out_1970164945047322285[4] = -nom_x[4] + true_x[4];
   out_1970164945047322285[5] = -nom_x[5] + true_x[5];
   out_1970164945047322285[6] = -nom_x[6] + true_x[6];
   out_1970164945047322285[7] = -nom_x[7] + true_x[7];
   out_1970164945047322285[8] = -nom_x[8] + true_x[8];
   out_1970164945047322285[9] = -nom_x[9] + true_x[9];
   out_1970164945047322285[10] = -nom_x[10] + true_x[10];
   out_1970164945047322285[11] = -nom_x[11] + true_x[11];
   out_1970164945047322285[12] = -nom_x[12] + true_x[12];
   out_1970164945047322285[13] = -nom_x[13] + true_x[13];
   out_1970164945047322285[14] = -nom_x[14] + true_x[14];
   out_1970164945047322285[15] = -nom_x[15] + true_x[15];
   out_1970164945047322285[16] = -nom_x[16] + true_x[16];
   out_1970164945047322285[17] = -nom_x[17] + true_x[17];
}
void H_mod_fun(double *state, double *out_755526174421445756) {
   out_755526174421445756[0] = 1.0;
   out_755526174421445756[1] = 0.0;
   out_755526174421445756[2] = 0.0;
   out_755526174421445756[3] = 0.0;
   out_755526174421445756[4] = 0.0;
   out_755526174421445756[5] = 0.0;
   out_755526174421445756[6] = 0.0;
   out_755526174421445756[7] = 0.0;
   out_755526174421445756[8] = 0.0;
   out_755526174421445756[9] = 0.0;
   out_755526174421445756[10] = 0.0;
   out_755526174421445756[11] = 0.0;
   out_755526174421445756[12] = 0.0;
   out_755526174421445756[13] = 0.0;
   out_755526174421445756[14] = 0.0;
   out_755526174421445756[15] = 0.0;
   out_755526174421445756[16] = 0.0;
   out_755526174421445756[17] = 0.0;
   out_755526174421445756[18] = 0.0;
   out_755526174421445756[19] = 1.0;
   out_755526174421445756[20] = 0.0;
   out_755526174421445756[21] = 0.0;
   out_755526174421445756[22] = 0.0;
   out_755526174421445756[23] = 0.0;
   out_755526174421445756[24] = 0.0;
   out_755526174421445756[25] = 0.0;
   out_755526174421445756[26] = 0.0;
   out_755526174421445756[27] = 0.0;
   out_755526174421445756[28] = 0.0;
   out_755526174421445756[29] = 0.0;
   out_755526174421445756[30] = 0.0;
   out_755526174421445756[31] = 0.0;
   out_755526174421445756[32] = 0.0;
   out_755526174421445756[33] = 0.0;
   out_755526174421445756[34] = 0.0;
   out_755526174421445756[35] = 0.0;
   out_755526174421445756[36] = 0.0;
   out_755526174421445756[37] = 0.0;
   out_755526174421445756[38] = 1.0;
   out_755526174421445756[39] = 0.0;
   out_755526174421445756[40] = 0.0;
   out_755526174421445756[41] = 0.0;
   out_755526174421445756[42] = 0.0;
   out_755526174421445756[43] = 0.0;
   out_755526174421445756[44] = 0.0;
   out_755526174421445756[45] = 0.0;
   out_755526174421445756[46] = 0.0;
   out_755526174421445756[47] = 0.0;
   out_755526174421445756[48] = 0.0;
   out_755526174421445756[49] = 0.0;
   out_755526174421445756[50] = 0.0;
   out_755526174421445756[51] = 0.0;
   out_755526174421445756[52] = 0.0;
   out_755526174421445756[53] = 0.0;
   out_755526174421445756[54] = 0.0;
   out_755526174421445756[55] = 0.0;
   out_755526174421445756[56] = 0.0;
   out_755526174421445756[57] = 1.0;
   out_755526174421445756[58] = 0.0;
   out_755526174421445756[59] = 0.0;
   out_755526174421445756[60] = 0.0;
   out_755526174421445756[61] = 0.0;
   out_755526174421445756[62] = 0.0;
   out_755526174421445756[63] = 0.0;
   out_755526174421445756[64] = 0.0;
   out_755526174421445756[65] = 0.0;
   out_755526174421445756[66] = 0.0;
   out_755526174421445756[67] = 0.0;
   out_755526174421445756[68] = 0.0;
   out_755526174421445756[69] = 0.0;
   out_755526174421445756[70] = 0.0;
   out_755526174421445756[71] = 0.0;
   out_755526174421445756[72] = 0.0;
   out_755526174421445756[73] = 0.0;
   out_755526174421445756[74] = 0.0;
   out_755526174421445756[75] = 0.0;
   out_755526174421445756[76] = 1.0;
   out_755526174421445756[77] = 0.0;
   out_755526174421445756[78] = 0.0;
   out_755526174421445756[79] = 0.0;
   out_755526174421445756[80] = 0.0;
   out_755526174421445756[81] = 0.0;
   out_755526174421445756[82] = 0.0;
   out_755526174421445756[83] = 0.0;
   out_755526174421445756[84] = 0.0;
   out_755526174421445756[85] = 0.0;
   out_755526174421445756[86] = 0.0;
   out_755526174421445756[87] = 0.0;
   out_755526174421445756[88] = 0.0;
   out_755526174421445756[89] = 0.0;
   out_755526174421445756[90] = 0.0;
   out_755526174421445756[91] = 0.0;
   out_755526174421445756[92] = 0.0;
   out_755526174421445756[93] = 0.0;
   out_755526174421445756[94] = 0.0;
   out_755526174421445756[95] = 1.0;
   out_755526174421445756[96] = 0.0;
   out_755526174421445756[97] = 0.0;
   out_755526174421445756[98] = 0.0;
   out_755526174421445756[99] = 0.0;
   out_755526174421445756[100] = 0.0;
   out_755526174421445756[101] = 0.0;
   out_755526174421445756[102] = 0.0;
   out_755526174421445756[103] = 0.0;
   out_755526174421445756[104] = 0.0;
   out_755526174421445756[105] = 0.0;
   out_755526174421445756[106] = 0.0;
   out_755526174421445756[107] = 0.0;
   out_755526174421445756[108] = 0.0;
   out_755526174421445756[109] = 0.0;
   out_755526174421445756[110] = 0.0;
   out_755526174421445756[111] = 0.0;
   out_755526174421445756[112] = 0.0;
   out_755526174421445756[113] = 0.0;
   out_755526174421445756[114] = 1.0;
   out_755526174421445756[115] = 0.0;
   out_755526174421445756[116] = 0.0;
   out_755526174421445756[117] = 0.0;
   out_755526174421445756[118] = 0.0;
   out_755526174421445756[119] = 0.0;
   out_755526174421445756[120] = 0.0;
   out_755526174421445756[121] = 0.0;
   out_755526174421445756[122] = 0.0;
   out_755526174421445756[123] = 0.0;
   out_755526174421445756[124] = 0.0;
   out_755526174421445756[125] = 0.0;
   out_755526174421445756[126] = 0.0;
   out_755526174421445756[127] = 0.0;
   out_755526174421445756[128] = 0.0;
   out_755526174421445756[129] = 0.0;
   out_755526174421445756[130] = 0.0;
   out_755526174421445756[131] = 0.0;
   out_755526174421445756[132] = 0.0;
   out_755526174421445756[133] = 1.0;
   out_755526174421445756[134] = 0.0;
   out_755526174421445756[135] = 0.0;
   out_755526174421445756[136] = 0.0;
   out_755526174421445756[137] = 0.0;
   out_755526174421445756[138] = 0.0;
   out_755526174421445756[139] = 0.0;
   out_755526174421445756[140] = 0.0;
   out_755526174421445756[141] = 0.0;
   out_755526174421445756[142] = 0.0;
   out_755526174421445756[143] = 0.0;
   out_755526174421445756[144] = 0.0;
   out_755526174421445756[145] = 0.0;
   out_755526174421445756[146] = 0.0;
   out_755526174421445756[147] = 0.0;
   out_755526174421445756[148] = 0.0;
   out_755526174421445756[149] = 0.0;
   out_755526174421445756[150] = 0.0;
   out_755526174421445756[151] = 0.0;
   out_755526174421445756[152] = 1.0;
   out_755526174421445756[153] = 0.0;
   out_755526174421445756[154] = 0.0;
   out_755526174421445756[155] = 0.0;
   out_755526174421445756[156] = 0.0;
   out_755526174421445756[157] = 0.0;
   out_755526174421445756[158] = 0.0;
   out_755526174421445756[159] = 0.0;
   out_755526174421445756[160] = 0.0;
   out_755526174421445756[161] = 0.0;
   out_755526174421445756[162] = 0.0;
   out_755526174421445756[163] = 0.0;
   out_755526174421445756[164] = 0.0;
   out_755526174421445756[165] = 0.0;
   out_755526174421445756[166] = 0.0;
   out_755526174421445756[167] = 0.0;
   out_755526174421445756[168] = 0.0;
   out_755526174421445756[169] = 0.0;
   out_755526174421445756[170] = 0.0;
   out_755526174421445756[171] = 1.0;
   out_755526174421445756[172] = 0.0;
   out_755526174421445756[173] = 0.0;
   out_755526174421445756[174] = 0.0;
   out_755526174421445756[175] = 0.0;
   out_755526174421445756[176] = 0.0;
   out_755526174421445756[177] = 0.0;
   out_755526174421445756[178] = 0.0;
   out_755526174421445756[179] = 0.0;
   out_755526174421445756[180] = 0.0;
   out_755526174421445756[181] = 0.0;
   out_755526174421445756[182] = 0.0;
   out_755526174421445756[183] = 0.0;
   out_755526174421445756[184] = 0.0;
   out_755526174421445756[185] = 0.0;
   out_755526174421445756[186] = 0.0;
   out_755526174421445756[187] = 0.0;
   out_755526174421445756[188] = 0.0;
   out_755526174421445756[189] = 0.0;
   out_755526174421445756[190] = 1.0;
   out_755526174421445756[191] = 0.0;
   out_755526174421445756[192] = 0.0;
   out_755526174421445756[193] = 0.0;
   out_755526174421445756[194] = 0.0;
   out_755526174421445756[195] = 0.0;
   out_755526174421445756[196] = 0.0;
   out_755526174421445756[197] = 0.0;
   out_755526174421445756[198] = 0.0;
   out_755526174421445756[199] = 0.0;
   out_755526174421445756[200] = 0.0;
   out_755526174421445756[201] = 0.0;
   out_755526174421445756[202] = 0.0;
   out_755526174421445756[203] = 0.0;
   out_755526174421445756[204] = 0.0;
   out_755526174421445756[205] = 0.0;
   out_755526174421445756[206] = 0.0;
   out_755526174421445756[207] = 0.0;
   out_755526174421445756[208] = 0.0;
   out_755526174421445756[209] = 1.0;
   out_755526174421445756[210] = 0.0;
   out_755526174421445756[211] = 0.0;
   out_755526174421445756[212] = 0.0;
   out_755526174421445756[213] = 0.0;
   out_755526174421445756[214] = 0.0;
   out_755526174421445756[215] = 0.0;
   out_755526174421445756[216] = 0.0;
   out_755526174421445756[217] = 0.0;
   out_755526174421445756[218] = 0.0;
   out_755526174421445756[219] = 0.0;
   out_755526174421445756[220] = 0.0;
   out_755526174421445756[221] = 0.0;
   out_755526174421445756[222] = 0.0;
   out_755526174421445756[223] = 0.0;
   out_755526174421445756[224] = 0.0;
   out_755526174421445756[225] = 0.0;
   out_755526174421445756[226] = 0.0;
   out_755526174421445756[227] = 0.0;
   out_755526174421445756[228] = 1.0;
   out_755526174421445756[229] = 0.0;
   out_755526174421445756[230] = 0.0;
   out_755526174421445756[231] = 0.0;
   out_755526174421445756[232] = 0.0;
   out_755526174421445756[233] = 0.0;
   out_755526174421445756[234] = 0.0;
   out_755526174421445756[235] = 0.0;
   out_755526174421445756[236] = 0.0;
   out_755526174421445756[237] = 0.0;
   out_755526174421445756[238] = 0.0;
   out_755526174421445756[239] = 0.0;
   out_755526174421445756[240] = 0.0;
   out_755526174421445756[241] = 0.0;
   out_755526174421445756[242] = 0.0;
   out_755526174421445756[243] = 0.0;
   out_755526174421445756[244] = 0.0;
   out_755526174421445756[245] = 0.0;
   out_755526174421445756[246] = 0.0;
   out_755526174421445756[247] = 1.0;
   out_755526174421445756[248] = 0.0;
   out_755526174421445756[249] = 0.0;
   out_755526174421445756[250] = 0.0;
   out_755526174421445756[251] = 0.0;
   out_755526174421445756[252] = 0.0;
   out_755526174421445756[253] = 0.0;
   out_755526174421445756[254] = 0.0;
   out_755526174421445756[255] = 0.0;
   out_755526174421445756[256] = 0.0;
   out_755526174421445756[257] = 0.0;
   out_755526174421445756[258] = 0.0;
   out_755526174421445756[259] = 0.0;
   out_755526174421445756[260] = 0.0;
   out_755526174421445756[261] = 0.0;
   out_755526174421445756[262] = 0.0;
   out_755526174421445756[263] = 0.0;
   out_755526174421445756[264] = 0.0;
   out_755526174421445756[265] = 0.0;
   out_755526174421445756[266] = 1.0;
   out_755526174421445756[267] = 0.0;
   out_755526174421445756[268] = 0.0;
   out_755526174421445756[269] = 0.0;
   out_755526174421445756[270] = 0.0;
   out_755526174421445756[271] = 0.0;
   out_755526174421445756[272] = 0.0;
   out_755526174421445756[273] = 0.0;
   out_755526174421445756[274] = 0.0;
   out_755526174421445756[275] = 0.0;
   out_755526174421445756[276] = 0.0;
   out_755526174421445756[277] = 0.0;
   out_755526174421445756[278] = 0.0;
   out_755526174421445756[279] = 0.0;
   out_755526174421445756[280] = 0.0;
   out_755526174421445756[281] = 0.0;
   out_755526174421445756[282] = 0.0;
   out_755526174421445756[283] = 0.0;
   out_755526174421445756[284] = 0.0;
   out_755526174421445756[285] = 1.0;
   out_755526174421445756[286] = 0.0;
   out_755526174421445756[287] = 0.0;
   out_755526174421445756[288] = 0.0;
   out_755526174421445756[289] = 0.0;
   out_755526174421445756[290] = 0.0;
   out_755526174421445756[291] = 0.0;
   out_755526174421445756[292] = 0.0;
   out_755526174421445756[293] = 0.0;
   out_755526174421445756[294] = 0.0;
   out_755526174421445756[295] = 0.0;
   out_755526174421445756[296] = 0.0;
   out_755526174421445756[297] = 0.0;
   out_755526174421445756[298] = 0.0;
   out_755526174421445756[299] = 0.0;
   out_755526174421445756[300] = 0.0;
   out_755526174421445756[301] = 0.0;
   out_755526174421445756[302] = 0.0;
   out_755526174421445756[303] = 0.0;
   out_755526174421445756[304] = 1.0;
   out_755526174421445756[305] = 0.0;
   out_755526174421445756[306] = 0.0;
   out_755526174421445756[307] = 0.0;
   out_755526174421445756[308] = 0.0;
   out_755526174421445756[309] = 0.0;
   out_755526174421445756[310] = 0.0;
   out_755526174421445756[311] = 0.0;
   out_755526174421445756[312] = 0.0;
   out_755526174421445756[313] = 0.0;
   out_755526174421445756[314] = 0.0;
   out_755526174421445756[315] = 0.0;
   out_755526174421445756[316] = 0.0;
   out_755526174421445756[317] = 0.0;
   out_755526174421445756[318] = 0.0;
   out_755526174421445756[319] = 0.0;
   out_755526174421445756[320] = 0.0;
   out_755526174421445756[321] = 0.0;
   out_755526174421445756[322] = 0.0;
   out_755526174421445756[323] = 1.0;
}
void f_fun(double *state, double dt, double *out_3677371884399014073) {
   out_3677371884399014073[0] = atan2((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), -(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]));
   out_3677371884399014073[1] = asin(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]));
   out_3677371884399014073[2] = atan2(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), -(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]));
   out_3677371884399014073[3] = dt*state[12] + state[3];
   out_3677371884399014073[4] = dt*state[13] + state[4];
   out_3677371884399014073[5] = dt*state[14] + state[5];
   out_3677371884399014073[6] = state[6];
   out_3677371884399014073[7] = state[7];
   out_3677371884399014073[8] = state[8];
   out_3677371884399014073[9] = state[9];
   out_3677371884399014073[10] = state[10];
   out_3677371884399014073[11] = state[11];
   out_3677371884399014073[12] = state[12];
   out_3677371884399014073[13] = state[13];
   out_3677371884399014073[14] = state[14];
   out_3677371884399014073[15] = state[15];
   out_3677371884399014073[16] = state[16];
   out_3677371884399014073[17] = state[17];
}
void F_fun(double *state, double dt, double *out_663397675647970276) {
   out_663397675647970276[0] = ((-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*cos(state[0])*cos(state[1]) - sin(state[0])*cos(dt*state[6])*cos(dt*state[7])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + ((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*cos(state[0])*cos(state[1]) - sin(dt*state[6])*sin(state[0])*cos(dt*state[7])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_663397675647970276[1] = ((-sin(dt*state[6])*sin(dt*state[8]) - sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*cos(state[1]) - (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*sin(state[1]) - sin(state[1])*cos(dt*state[6])*cos(dt*state[7])*cos(state[0]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*sin(state[1]) + (-sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) + sin(dt*state[8])*cos(dt*state[6]))*cos(state[1]) - sin(dt*state[6])*sin(state[1])*cos(dt*state[7])*cos(state[0]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_663397675647970276[2] = 0;
   out_663397675647970276[3] = 0;
   out_663397675647970276[4] = 0;
   out_663397675647970276[5] = 0;
   out_663397675647970276[6] = (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(dt*cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*sin(dt*state[8]) - dt*sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-dt*sin(dt*state[6])*cos(dt*state[8]) + dt*sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) - dt*cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (dt*sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_663397675647970276[7] = (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[6])*sin(dt*state[7])*cos(state[0])*cos(state[1]) + dt*sin(dt*state[6])*sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) - dt*sin(dt*state[6])*sin(state[1])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[7])*cos(dt*state[6])*cos(state[0])*cos(state[1]) + dt*sin(dt*state[8])*sin(state[0])*cos(dt*state[6])*cos(dt*state[7])*cos(state[1]) - dt*sin(state[1])*cos(dt*state[6])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_663397675647970276[8] = ((dt*sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + dt*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (dt*sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + ((dt*sin(dt*state[6])*sin(dt*state[8]) + dt*sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*cos(dt*state[8]) + dt*sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_663397675647970276[9] = 0;
   out_663397675647970276[10] = 0;
   out_663397675647970276[11] = 0;
   out_663397675647970276[12] = 0;
   out_663397675647970276[13] = 0;
   out_663397675647970276[14] = 0;
   out_663397675647970276[15] = 0;
   out_663397675647970276[16] = 0;
   out_663397675647970276[17] = 0;
   out_663397675647970276[18] = (-sin(dt*state[7])*sin(state[0])*cos(state[1]) - sin(dt*state[8])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_663397675647970276[19] = (-sin(dt*state[7])*sin(state[1])*cos(state[0]) + sin(dt*state[8])*sin(state[0])*sin(state[1])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_663397675647970276[20] = 0;
   out_663397675647970276[21] = 0;
   out_663397675647970276[22] = 0;
   out_663397675647970276[23] = 0;
   out_663397675647970276[24] = 0;
   out_663397675647970276[25] = (dt*sin(dt*state[7])*sin(dt*state[8])*sin(state[0])*cos(state[1]) - dt*sin(dt*state[7])*sin(state[1])*cos(dt*state[8]) + dt*cos(dt*state[7])*cos(state[0])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_663397675647970276[26] = (-dt*sin(dt*state[8])*sin(state[1])*cos(dt*state[7]) - dt*sin(state[0])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_663397675647970276[27] = 0;
   out_663397675647970276[28] = 0;
   out_663397675647970276[29] = 0;
   out_663397675647970276[30] = 0;
   out_663397675647970276[31] = 0;
   out_663397675647970276[32] = 0;
   out_663397675647970276[33] = 0;
   out_663397675647970276[34] = 0;
   out_663397675647970276[35] = 0;
   out_663397675647970276[36] = ((sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[7]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[7]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_663397675647970276[37] = (-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(-sin(dt*state[7])*sin(state[2])*cos(state[0])*cos(state[1]) + sin(dt*state[8])*sin(state[0])*sin(state[2])*cos(dt*state[7])*cos(state[1]) - sin(state[1])*sin(state[2])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*(-sin(dt*state[7])*cos(state[0])*cos(state[1])*cos(state[2]) + sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1])*cos(state[2]) - sin(state[1])*cos(dt*state[7])*cos(dt*state[8])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_663397675647970276[38] = ((-sin(state[0])*sin(state[2]) - sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (-sin(state[0])*sin(state[1])*sin(state[2]) - cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_663397675647970276[39] = 0;
   out_663397675647970276[40] = 0;
   out_663397675647970276[41] = 0;
   out_663397675647970276[42] = 0;
   out_663397675647970276[43] = (-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(dt*(sin(state[0])*cos(state[2]) - sin(state[1])*sin(state[2])*cos(state[0]))*cos(dt*state[7]) - dt*(sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[7])*sin(dt*state[8]) - dt*sin(dt*state[7])*sin(state[2])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*(dt*(-sin(state[0])*sin(state[2]) - sin(state[1])*cos(state[0])*cos(state[2]))*cos(dt*state[7]) - dt*(sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[7])*sin(dt*state[8]) - dt*sin(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_663397675647970276[44] = (dt*(sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*cos(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*sin(state[2])*cos(dt*state[7])*cos(state[1]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + (dt*(sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*cos(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[7])*cos(state[1])*cos(state[2]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_663397675647970276[45] = 0;
   out_663397675647970276[46] = 0;
   out_663397675647970276[47] = 0;
   out_663397675647970276[48] = 0;
   out_663397675647970276[49] = 0;
   out_663397675647970276[50] = 0;
   out_663397675647970276[51] = 0;
   out_663397675647970276[52] = 0;
   out_663397675647970276[53] = 0;
   out_663397675647970276[54] = 0;
   out_663397675647970276[55] = 0;
   out_663397675647970276[56] = 0;
   out_663397675647970276[57] = 1;
   out_663397675647970276[58] = 0;
   out_663397675647970276[59] = 0;
   out_663397675647970276[60] = 0;
   out_663397675647970276[61] = 0;
   out_663397675647970276[62] = 0;
   out_663397675647970276[63] = 0;
   out_663397675647970276[64] = 0;
   out_663397675647970276[65] = 0;
   out_663397675647970276[66] = dt;
   out_663397675647970276[67] = 0;
   out_663397675647970276[68] = 0;
   out_663397675647970276[69] = 0;
   out_663397675647970276[70] = 0;
   out_663397675647970276[71] = 0;
   out_663397675647970276[72] = 0;
   out_663397675647970276[73] = 0;
   out_663397675647970276[74] = 0;
   out_663397675647970276[75] = 0;
   out_663397675647970276[76] = 1;
   out_663397675647970276[77] = 0;
   out_663397675647970276[78] = 0;
   out_663397675647970276[79] = 0;
   out_663397675647970276[80] = 0;
   out_663397675647970276[81] = 0;
   out_663397675647970276[82] = 0;
   out_663397675647970276[83] = 0;
   out_663397675647970276[84] = 0;
   out_663397675647970276[85] = dt;
   out_663397675647970276[86] = 0;
   out_663397675647970276[87] = 0;
   out_663397675647970276[88] = 0;
   out_663397675647970276[89] = 0;
   out_663397675647970276[90] = 0;
   out_663397675647970276[91] = 0;
   out_663397675647970276[92] = 0;
   out_663397675647970276[93] = 0;
   out_663397675647970276[94] = 0;
   out_663397675647970276[95] = 1;
   out_663397675647970276[96] = 0;
   out_663397675647970276[97] = 0;
   out_663397675647970276[98] = 0;
   out_663397675647970276[99] = 0;
   out_663397675647970276[100] = 0;
   out_663397675647970276[101] = 0;
   out_663397675647970276[102] = 0;
   out_663397675647970276[103] = 0;
   out_663397675647970276[104] = dt;
   out_663397675647970276[105] = 0;
   out_663397675647970276[106] = 0;
   out_663397675647970276[107] = 0;
   out_663397675647970276[108] = 0;
   out_663397675647970276[109] = 0;
   out_663397675647970276[110] = 0;
   out_663397675647970276[111] = 0;
   out_663397675647970276[112] = 0;
   out_663397675647970276[113] = 0;
   out_663397675647970276[114] = 1;
   out_663397675647970276[115] = 0;
   out_663397675647970276[116] = 0;
   out_663397675647970276[117] = 0;
   out_663397675647970276[118] = 0;
   out_663397675647970276[119] = 0;
   out_663397675647970276[120] = 0;
   out_663397675647970276[121] = 0;
   out_663397675647970276[122] = 0;
   out_663397675647970276[123] = 0;
   out_663397675647970276[124] = 0;
   out_663397675647970276[125] = 0;
   out_663397675647970276[126] = 0;
   out_663397675647970276[127] = 0;
   out_663397675647970276[128] = 0;
   out_663397675647970276[129] = 0;
   out_663397675647970276[130] = 0;
   out_663397675647970276[131] = 0;
   out_663397675647970276[132] = 0;
   out_663397675647970276[133] = 1;
   out_663397675647970276[134] = 0;
   out_663397675647970276[135] = 0;
   out_663397675647970276[136] = 0;
   out_663397675647970276[137] = 0;
   out_663397675647970276[138] = 0;
   out_663397675647970276[139] = 0;
   out_663397675647970276[140] = 0;
   out_663397675647970276[141] = 0;
   out_663397675647970276[142] = 0;
   out_663397675647970276[143] = 0;
   out_663397675647970276[144] = 0;
   out_663397675647970276[145] = 0;
   out_663397675647970276[146] = 0;
   out_663397675647970276[147] = 0;
   out_663397675647970276[148] = 0;
   out_663397675647970276[149] = 0;
   out_663397675647970276[150] = 0;
   out_663397675647970276[151] = 0;
   out_663397675647970276[152] = 1;
   out_663397675647970276[153] = 0;
   out_663397675647970276[154] = 0;
   out_663397675647970276[155] = 0;
   out_663397675647970276[156] = 0;
   out_663397675647970276[157] = 0;
   out_663397675647970276[158] = 0;
   out_663397675647970276[159] = 0;
   out_663397675647970276[160] = 0;
   out_663397675647970276[161] = 0;
   out_663397675647970276[162] = 0;
   out_663397675647970276[163] = 0;
   out_663397675647970276[164] = 0;
   out_663397675647970276[165] = 0;
   out_663397675647970276[166] = 0;
   out_663397675647970276[167] = 0;
   out_663397675647970276[168] = 0;
   out_663397675647970276[169] = 0;
   out_663397675647970276[170] = 0;
   out_663397675647970276[171] = 1;
   out_663397675647970276[172] = 0;
   out_663397675647970276[173] = 0;
   out_663397675647970276[174] = 0;
   out_663397675647970276[175] = 0;
   out_663397675647970276[176] = 0;
   out_663397675647970276[177] = 0;
   out_663397675647970276[178] = 0;
   out_663397675647970276[179] = 0;
   out_663397675647970276[180] = 0;
   out_663397675647970276[181] = 0;
   out_663397675647970276[182] = 0;
   out_663397675647970276[183] = 0;
   out_663397675647970276[184] = 0;
   out_663397675647970276[185] = 0;
   out_663397675647970276[186] = 0;
   out_663397675647970276[187] = 0;
   out_663397675647970276[188] = 0;
   out_663397675647970276[189] = 0;
   out_663397675647970276[190] = 1;
   out_663397675647970276[191] = 0;
   out_663397675647970276[192] = 0;
   out_663397675647970276[193] = 0;
   out_663397675647970276[194] = 0;
   out_663397675647970276[195] = 0;
   out_663397675647970276[196] = 0;
   out_663397675647970276[197] = 0;
   out_663397675647970276[198] = 0;
   out_663397675647970276[199] = 0;
   out_663397675647970276[200] = 0;
   out_663397675647970276[201] = 0;
   out_663397675647970276[202] = 0;
   out_663397675647970276[203] = 0;
   out_663397675647970276[204] = 0;
   out_663397675647970276[205] = 0;
   out_663397675647970276[206] = 0;
   out_663397675647970276[207] = 0;
   out_663397675647970276[208] = 0;
   out_663397675647970276[209] = 1;
   out_663397675647970276[210] = 0;
   out_663397675647970276[211] = 0;
   out_663397675647970276[212] = 0;
   out_663397675647970276[213] = 0;
   out_663397675647970276[214] = 0;
   out_663397675647970276[215] = 0;
   out_663397675647970276[216] = 0;
   out_663397675647970276[217] = 0;
   out_663397675647970276[218] = 0;
   out_663397675647970276[219] = 0;
   out_663397675647970276[220] = 0;
   out_663397675647970276[221] = 0;
   out_663397675647970276[222] = 0;
   out_663397675647970276[223] = 0;
   out_663397675647970276[224] = 0;
   out_663397675647970276[225] = 0;
   out_663397675647970276[226] = 0;
   out_663397675647970276[227] = 0;
   out_663397675647970276[228] = 1;
   out_663397675647970276[229] = 0;
   out_663397675647970276[230] = 0;
   out_663397675647970276[231] = 0;
   out_663397675647970276[232] = 0;
   out_663397675647970276[233] = 0;
   out_663397675647970276[234] = 0;
   out_663397675647970276[235] = 0;
   out_663397675647970276[236] = 0;
   out_663397675647970276[237] = 0;
   out_663397675647970276[238] = 0;
   out_663397675647970276[239] = 0;
   out_663397675647970276[240] = 0;
   out_663397675647970276[241] = 0;
   out_663397675647970276[242] = 0;
   out_663397675647970276[243] = 0;
   out_663397675647970276[244] = 0;
   out_663397675647970276[245] = 0;
   out_663397675647970276[246] = 0;
   out_663397675647970276[247] = 1;
   out_663397675647970276[248] = 0;
   out_663397675647970276[249] = 0;
   out_663397675647970276[250] = 0;
   out_663397675647970276[251] = 0;
   out_663397675647970276[252] = 0;
   out_663397675647970276[253] = 0;
   out_663397675647970276[254] = 0;
   out_663397675647970276[255] = 0;
   out_663397675647970276[256] = 0;
   out_663397675647970276[257] = 0;
   out_663397675647970276[258] = 0;
   out_663397675647970276[259] = 0;
   out_663397675647970276[260] = 0;
   out_663397675647970276[261] = 0;
   out_663397675647970276[262] = 0;
   out_663397675647970276[263] = 0;
   out_663397675647970276[264] = 0;
   out_663397675647970276[265] = 0;
   out_663397675647970276[266] = 1;
   out_663397675647970276[267] = 0;
   out_663397675647970276[268] = 0;
   out_663397675647970276[269] = 0;
   out_663397675647970276[270] = 0;
   out_663397675647970276[271] = 0;
   out_663397675647970276[272] = 0;
   out_663397675647970276[273] = 0;
   out_663397675647970276[274] = 0;
   out_663397675647970276[275] = 0;
   out_663397675647970276[276] = 0;
   out_663397675647970276[277] = 0;
   out_663397675647970276[278] = 0;
   out_663397675647970276[279] = 0;
   out_663397675647970276[280] = 0;
   out_663397675647970276[281] = 0;
   out_663397675647970276[282] = 0;
   out_663397675647970276[283] = 0;
   out_663397675647970276[284] = 0;
   out_663397675647970276[285] = 1;
   out_663397675647970276[286] = 0;
   out_663397675647970276[287] = 0;
   out_663397675647970276[288] = 0;
   out_663397675647970276[289] = 0;
   out_663397675647970276[290] = 0;
   out_663397675647970276[291] = 0;
   out_663397675647970276[292] = 0;
   out_663397675647970276[293] = 0;
   out_663397675647970276[294] = 0;
   out_663397675647970276[295] = 0;
   out_663397675647970276[296] = 0;
   out_663397675647970276[297] = 0;
   out_663397675647970276[298] = 0;
   out_663397675647970276[299] = 0;
   out_663397675647970276[300] = 0;
   out_663397675647970276[301] = 0;
   out_663397675647970276[302] = 0;
   out_663397675647970276[303] = 0;
   out_663397675647970276[304] = 1;
   out_663397675647970276[305] = 0;
   out_663397675647970276[306] = 0;
   out_663397675647970276[307] = 0;
   out_663397675647970276[308] = 0;
   out_663397675647970276[309] = 0;
   out_663397675647970276[310] = 0;
   out_663397675647970276[311] = 0;
   out_663397675647970276[312] = 0;
   out_663397675647970276[313] = 0;
   out_663397675647970276[314] = 0;
   out_663397675647970276[315] = 0;
   out_663397675647970276[316] = 0;
   out_663397675647970276[317] = 0;
   out_663397675647970276[318] = 0;
   out_663397675647970276[319] = 0;
   out_663397675647970276[320] = 0;
   out_663397675647970276[321] = 0;
   out_663397675647970276[322] = 0;
   out_663397675647970276[323] = 1;
}
void h_4(double *state, double *unused, double *out_7443258878815348214) {
   out_7443258878815348214[0] = state[6] + state[9];
   out_7443258878815348214[1] = state[7] + state[10];
   out_7443258878815348214[2] = state[8] + state[11];
}
void H_4(double *state, double *unused, double *out_442421307461452348) {
   out_442421307461452348[0] = 0;
   out_442421307461452348[1] = 0;
   out_442421307461452348[2] = 0;
   out_442421307461452348[3] = 0;
   out_442421307461452348[4] = 0;
   out_442421307461452348[5] = 0;
   out_442421307461452348[6] = 1;
   out_442421307461452348[7] = 0;
   out_442421307461452348[8] = 0;
   out_442421307461452348[9] = 1;
   out_442421307461452348[10] = 0;
   out_442421307461452348[11] = 0;
   out_442421307461452348[12] = 0;
   out_442421307461452348[13] = 0;
   out_442421307461452348[14] = 0;
   out_442421307461452348[15] = 0;
   out_442421307461452348[16] = 0;
   out_442421307461452348[17] = 0;
   out_442421307461452348[18] = 0;
   out_442421307461452348[19] = 0;
   out_442421307461452348[20] = 0;
   out_442421307461452348[21] = 0;
   out_442421307461452348[22] = 0;
   out_442421307461452348[23] = 0;
   out_442421307461452348[24] = 0;
   out_442421307461452348[25] = 1;
   out_442421307461452348[26] = 0;
   out_442421307461452348[27] = 0;
   out_442421307461452348[28] = 1;
   out_442421307461452348[29] = 0;
   out_442421307461452348[30] = 0;
   out_442421307461452348[31] = 0;
   out_442421307461452348[32] = 0;
   out_442421307461452348[33] = 0;
   out_442421307461452348[34] = 0;
   out_442421307461452348[35] = 0;
   out_442421307461452348[36] = 0;
   out_442421307461452348[37] = 0;
   out_442421307461452348[38] = 0;
   out_442421307461452348[39] = 0;
   out_442421307461452348[40] = 0;
   out_442421307461452348[41] = 0;
   out_442421307461452348[42] = 0;
   out_442421307461452348[43] = 0;
   out_442421307461452348[44] = 1;
   out_442421307461452348[45] = 0;
   out_442421307461452348[46] = 0;
   out_442421307461452348[47] = 1;
   out_442421307461452348[48] = 0;
   out_442421307461452348[49] = 0;
   out_442421307461452348[50] = 0;
   out_442421307461452348[51] = 0;
   out_442421307461452348[52] = 0;
   out_442421307461452348[53] = 0;
}
void h_10(double *state, double *unused, double *out_6538590839038528319) {
   out_6538590839038528319[0] = 9.8100000000000005*sin(state[1]) - state[4]*state[8] + state[5]*state[7] + state[12] + state[15];
   out_6538590839038528319[1] = -9.8100000000000005*sin(state[0])*cos(state[1]) + state[3]*state[8] - state[5]*state[6] + state[13] + state[16];
   out_6538590839038528319[2] = -9.8100000000000005*cos(state[0])*cos(state[1]) - state[3]*state[7] + state[4]*state[6] + state[14] + state[17];
}
void H_10(double *state, double *unused, double *out_1931000376780675843) {
   out_1931000376780675843[0] = 0;
   out_1931000376780675843[1] = 9.8100000000000005*cos(state[1]);
   out_1931000376780675843[2] = 0;
   out_1931000376780675843[3] = 0;
   out_1931000376780675843[4] = -state[8];
   out_1931000376780675843[5] = state[7];
   out_1931000376780675843[6] = 0;
   out_1931000376780675843[7] = state[5];
   out_1931000376780675843[8] = -state[4];
   out_1931000376780675843[9] = 0;
   out_1931000376780675843[10] = 0;
   out_1931000376780675843[11] = 0;
   out_1931000376780675843[12] = 1;
   out_1931000376780675843[13] = 0;
   out_1931000376780675843[14] = 0;
   out_1931000376780675843[15] = 1;
   out_1931000376780675843[16] = 0;
   out_1931000376780675843[17] = 0;
   out_1931000376780675843[18] = -9.8100000000000005*cos(state[0])*cos(state[1]);
   out_1931000376780675843[19] = 9.8100000000000005*sin(state[0])*sin(state[1]);
   out_1931000376780675843[20] = 0;
   out_1931000376780675843[21] = state[8];
   out_1931000376780675843[22] = 0;
   out_1931000376780675843[23] = -state[6];
   out_1931000376780675843[24] = -state[5];
   out_1931000376780675843[25] = 0;
   out_1931000376780675843[26] = state[3];
   out_1931000376780675843[27] = 0;
   out_1931000376780675843[28] = 0;
   out_1931000376780675843[29] = 0;
   out_1931000376780675843[30] = 0;
   out_1931000376780675843[31] = 1;
   out_1931000376780675843[32] = 0;
   out_1931000376780675843[33] = 0;
   out_1931000376780675843[34] = 1;
   out_1931000376780675843[35] = 0;
   out_1931000376780675843[36] = 9.8100000000000005*sin(state[0])*cos(state[1]);
   out_1931000376780675843[37] = 9.8100000000000005*sin(state[1])*cos(state[0]);
   out_1931000376780675843[38] = 0;
   out_1931000376780675843[39] = -state[7];
   out_1931000376780675843[40] = state[6];
   out_1931000376780675843[41] = 0;
   out_1931000376780675843[42] = state[4];
   out_1931000376780675843[43] = -state[3];
   out_1931000376780675843[44] = 0;
   out_1931000376780675843[45] = 0;
   out_1931000376780675843[46] = 0;
   out_1931000376780675843[47] = 0;
   out_1931000376780675843[48] = 0;
   out_1931000376780675843[49] = 0;
   out_1931000376780675843[50] = 1;
   out_1931000376780675843[51] = 0;
   out_1931000376780675843[52] = 0;
   out_1931000376780675843[53] = 1;
}
void h_13(double *state, double *unused, double *out_5562882792733924299) {
   out_5562882792733924299[0] = state[3];
   out_5562882792733924299[1] = state[4];
   out_5562882792733924299[2] = state[5];
}
void H_13(double *state, double *unused, double *out_3654695132793785149) {
   out_3654695132793785149[0] = 0;
   out_3654695132793785149[1] = 0;
   out_3654695132793785149[2] = 0;
   out_3654695132793785149[3] = 1;
   out_3654695132793785149[4] = 0;
   out_3654695132793785149[5] = 0;
   out_3654695132793785149[6] = 0;
   out_3654695132793785149[7] = 0;
   out_3654695132793785149[8] = 0;
   out_3654695132793785149[9] = 0;
   out_3654695132793785149[10] = 0;
   out_3654695132793785149[11] = 0;
   out_3654695132793785149[12] = 0;
   out_3654695132793785149[13] = 0;
   out_3654695132793785149[14] = 0;
   out_3654695132793785149[15] = 0;
   out_3654695132793785149[16] = 0;
   out_3654695132793785149[17] = 0;
   out_3654695132793785149[18] = 0;
   out_3654695132793785149[19] = 0;
   out_3654695132793785149[20] = 0;
   out_3654695132793785149[21] = 0;
   out_3654695132793785149[22] = 1;
   out_3654695132793785149[23] = 0;
   out_3654695132793785149[24] = 0;
   out_3654695132793785149[25] = 0;
   out_3654695132793785149[26] = 0;
   out_3654695132793785149[27] = 0;
   out_3654695132793785149[28] = 0;
   out_3654695132793785149[29] = 0;
   out_3654695132793785149[30] = 0;
   out_3654695132793785149[31] = 0;
   out_3654695132793785149[32] = 0;
   out_3654695132793785149[33] = 0;
   out_3654695132793785149[34] = 0;
   out_3654695132793785149[35] = 0;
   out_3654695132793785149[36] = 0;
   out_3654695132793785149[37] = 0;
   out_3654695132793785149[38] = 0;
   out_3654695132793785149[39] = 0;
   out_3654695132793785149[40] = 0;
   out_3654695132793785149[41] = 1;
   out_3654695132793785149[42] = 0;
   out_3654695132793785149[43] = 0;
   out_3654695132793785149[44] = 0;
   out_3654695132793785149[45] = 0;
   out_3654695132793785149[46] = 0;
   out_3654695132793785149[47] = 0;
   out_3654695132793785149[48] = 0;
   out_3654695132793785149[49] = 0;
   out_3654695132793785149[50] = 0;
   out_3654695132793785149[51] = 0;
   out_3654695132793785149[52] = 0;
   out_3654695132793785149[53] = 0;
}
void h_14(double *state, double *unused, double *out_7679846457276660545) {
   out_7679846457276660545[0] = state[6];
   out_7679846457276660545[1] = state[7];
   out_7679846457276660545[2] = state[8];
}
void H_14(double *state, double *unused, double *out_4405662163800936877) {
   out_4405662163800936877[0] = 0;
   out_4405662163800936877[1] = 0;
   out_4405662163800936877[2] = 0;
   out_4405662163800936877[3] = 0;
   out_4405662163800936877[4] = 0;
   out_4405662163800936877[5] = 0;
   out_4405662163800936877[6] = 1;
   out_4405662163800936877[7] = 0;
   out_4405662163800936877[8] = 0;
   out_4405662163800936877[9] = 0;
   out_4405662163800936877[10] = 0;
   out_4405662163800936877[11] = 0;
   out_4405662163800936877[12] = 0;
   out_4405662163800936877[13] = 0;
   out_4405662163800936877[14] = 0;
   out_4405662163800936877[15] = 0;
   out_4405662163800936877[16] = 0;
   out_4405662163800936877[17] = 0;
   out_4405662163800936877[18] = 0;
   out_4405662163800936877[19] = 0;
   out_4405662163800936877[20] = 0;
   out_4405662163800936877[21] = 0;
   out_4405662163800936877[22] = 0;
   out_4405662163800936877[23] = 0;
   out_4405662163800936877[24] = 0;
   out_4405662163800936877[25] = 1;
   out_4405662163800936877[26] = 0;
   out_4405662163800936877[27] = 0;
   out_4405662163800936877[28] = 0;
   out_4405662163800936877[29] = 0;
   out_4405662163800936877[30] = 0;
   out_4405662163800936877[31] = 0;
   out_4405662163800936877[32] = 0;
   out_4405662163800936877[33] = 0;
   out_4405662163800936877[34] = 0;
   out_4405662163800936877[35] = 0;
   out_4405662163800936877[36] = 0;
   out_4405662163800936877[37] = 0;
   out_4405662163800936877[38] = 0;
   out_4405662163800936877[39] = 0;
   out_4405662163800936877[40] = 0;
   out_4405662163800936877[41] = 0;
   out_4405662163800936877[42] = 0;
   out_4405662163800936877[43] = 0;
   out_4405662163800936877[44] = 1;
   out_4405662163800936877[45] = 0;
   out_4405662163800936877[46] = 0;
   out_4405662163800936877[47] = 0;
   out_4405662163800936877[48] = 0;
   out_4405662163800936877[49] = 0;
   out_4405662163800936877[50] = 0;
   out_4405662163800936877[51] = 0;
   out_4405662163800936877[52] = 0;
   out_4405662163800936877[53] = 0;
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
void pose_err_fun(double *nom_x, double *delta_x, double *out_6205306553489213410) {
  err_fun(nom_x, delta_x, out_6205306553489213410);
}
void pose_inv_err_fun(double *nom_x, double *true_x, double *out_1970164945047322285) {
  inv_err_fun(nom_x, true_x, out_1970164945047322285);
}
void pose_H_mod_fun(double *state, double *out_755526174421445756) {
  H_mod_fun(state, out_755526174421445756);
}
void pose_f_fun(double *state, double dt, double *out_3677371884399014073) {
  f_fun(state,  dt, out_3677371884399014073);
}
void pose_F_fun(double *state, double dt, double *out_663397675647970276) {
  F_fun(state,  dt, out_663397675647970276);
}
void pose_h_4(double *state, double *unused, double *out_7443258878815348214) {
  h_4(state, unused, out_7443258878815348214);
}
void pose_H_4(double *state, double *unused, double *out_442421307461452348) {
  H_4(state, unused, out_442421307461452348);
}
void pose_h_10(double *state, double *unused, double *out_6538590839038528319) {
  h_10(state, unused, out_6538590839038528319);
}
void pose_H_10(double *state, double *unused, double *out_1931000376780675843) {
  H_10(state, unused, out_1931000376780675843);
}
void pose_h_13(double *state, double *unused, double *out_5562882792733924299) {
  h_13(state, unused, out_5562882792733924299);
}
void pose_H_13(double *state, double *unused, double *out_3654695132793785149) {
  H_13(state, unused, out_3654695132793785149);
}
void pose_h_14(double *state, double *unused, double *out_7679846457276660545) {
  h_14(state, unused, out_7679846457276660545);
}
void pose_H_14(double *state, double *unused, double *out_4405662163800936877) {
  H_14(state, unused, out_4405662163800936877);
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
