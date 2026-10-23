#pragma once

static bool toyota_prius_sdsu_param(uint16_t param) {
  return (param == 0x8042U) || (param == 0x8242U);
}

static bool toyota_prius_sdsu(void) {
  return toyota_prius_sdsu_param(current_safety_param);
}

static bool toyota_prius_sdsu_ambiguous = false;

static bool toyota_camera_2aa_param(uint16_t param) {
  return (param == 0xC049U) || (param == 0xC249U);
}

static bool toyota_camera_2aa(void) {
  return toyota_camera_2aa_param(current_safety_param);
}

static bool toyota_camera_2aa_ambiguous = false;

static bool toyota_legacy_advert_param(uint16_t param) {
  return (param == 0x9449U) || (param == 0x9549U) || (param == 0x9558U) || (param == 0x9564U) || (param == 0x9649U) || (param == 0x9749U) || (param == 0x9758U) || (param == 0x9764U) || (param == 0xD44DU) || (param == 0xD549U) || (param == 0xD64DU) || (param == 0xD749U);
}

static bool toyota_legacy_advert(void) {
  return toyota_legacy_advert_param(current_safety_param);
}


static bool toyota_aol_enabled = false;
static bool toyota_pedal = false;
static bool toyota_alt_cruise = false;

static bool toyota_aol_secoc = false;
static bool toyota_aol_stock = false;
static bool toyota_aol_lta = false;
static bool toyota_aol_rav4h_filter = false;
static bool toyota_sdsu_status = false;
static bool toyota_eps8_sdsu = false;
static bool toyota_legacy_sdsu = false;
static bool toyota_sdsu_control = false;
static bool toyota_aol_main = false;
static bool toyota_aol_drive = false;
static bool toyota_aol_doors_closed = false;
static bool toyota_aol_belt = false;
static bool toyota_aol_eps = false;
static bool toyota_aol_seen[4] = {false, false, false, false};
static uint32_t toyota_aol_ts[4] = {0U, 0U, 0U, 0U};

static void toyota_aol_reset(void) {
  toyota_sdsu_control = false;
  toyota_aol_main = false;
  toyota_aol_drive = false;
  toyota_aol_doors_closed = false;
  toyota_aol_belt = false;
  toyota_aol_eps = false;
  for (unsigned int i = 0U; i < 4U; i++) {
    toyota_aol_seen[i] = false;
    toyota_aol_ts[i] = 0U;
  }
}

static uint8_t toyota_aol_request(void) {
  uint8_t request = 0U;
  if (heartbeat_engaged && aol_rx_healthy() && !relay_malfunction &&
      (safety_get_ts_elapsed(microsecond_timer_get(), aol_host_request_ts) <= AOL_HOST_REQUEST_TIMEOUT_US)) {
    request = aol_host_axis_mask & (toyota_aol_stock ? 1U : 3U);
  }
  return request;
}

static uint8_t toyota_aol_permission(void) {
  const uint8_t request = toyota_aol_request();
  static const uint32_t source_timeout[4] = {303031U, 10000000U, 3333334U, 400000U};
  bool fresh = true;
  for (unsigned int i = 0U; i < 4U; i++) {
    const uint32_t timeout = ((i == 1U) && toyota_aol_secoc) ? 200000U : source_timeout[i];
    fresh &= toyota_aol_seen[i] && (safety_get_ts_elapsed(microsecond_timer_get(), toyota_aol_ts[i]) <= timeout);
  }
  uint8_t permission = 0U;
  if (fresh && toyota_aol_main && toyota_aol_drive && toyota_aol_doors_closed && toyota_aol_eps &&
      (!toyota_camera_2aa() || !toyota_camera_2aa_ambiguous) &&
      (!toyota_prius_sdsu() || !toyota_prius_sdsu_ambiguous)) {
    permission = request & 1U;
    if (!toyota_aol_stock && controls_allowed && toyota_aol_belt && !gas_pressed && !brake_pressed &&
        (!toyota_sdsu_status || toyota_sdsu_control)) {
      permission |= request & 2U;
    }
  }
  return permission;
}

static void toyota_aol_observe(const CANPacket_t *msg) {
  const uint32_t gear_addr = toyota_aol_secoc ? 0x127U : 0x3BCU;
  const uint32_t main_addr = toyota_alt_cruise ? 0x365U : 0x1D3U;
  unsigned int expected_len = 8U;
  if (toyota_alt_cruise && (msg->addr == main_addr)) {
    expected_len = 7U;
  } else if ((toyota_aol_rav4h_filter || toyota_alt_cruise || toyota_legacy_sdsu || toyota_legacy_advert()) && (msg->addr == 0x262U)) {
    expected_len = 5U;
  } else {
  }
  if ((toyota_aol_enabled || toyota_legacy_advert() || toyota_camera_2aa() || toyota_prius_sdsu()) && (msg->bus == 0U) && (GET_LEN(msg) != expected_len)) {
    unsigned int index = 4U;
    if (msg->addr == main_addr) {
      index = 0U;
    } else if (msg->addr == gear_addr) {
      index = 1U;
    } else if (msg->addr == 0x620U) {
      index = 2U;
    } else if (msg->addr == 0x262U) {
      index = 3U;
    } else {
    }
    if (index < 4U) {
      toyota_aol_seen[index] = false;
    }
  } else if ((toyota_aol_enabled || toyota_legacy_advert() || toyota_camera_2aa() || toyota_prius_sdsu()) && (msg->bus == 0U) && (GET_LEN(msg) == expected_len)) {
    unsigned int index = 4U;
    if (msg->addr == main_addr) {
      index = 0U;
      toyota_aol_main = toyota_alt_cruise ? GET_BIT(msg, 0U) : (GET_BIT(msg, 15U) && !GET_BIT(msg, 47U));
    } else if (msg->addr == gear_addr) {
      index = 1U;
      if (toyota_aol_secoc) {
        const unsigned int gear = msg->data[5] >> 4U;
        toyota_aol_drive = (gear == 3U) || (gear == 4U);
      } else {
        const unsigned int gear = msg->data[1] & 0x3FU;
        toyota_aol_drive = (gear == 0U) || (gear == 1U);
      }
    } else if (msg->addr == 0x620U) {
      index = 2U;
      toyota_aol_doors_closed = (msg->data[5] & 0x3CU) == 0U;
      toyota_aol_belt = !GET_BIT(msg, 62U);
    } else if (msg->addr == 0x262U) {
      index = 3U;
      const unsigned int state = (msg->data[3] >> 1U) & 0x7FU;
      toyota_aol_eps = (state != 0U) && (state != 9U) && (state != 11U) && (state != 21U) &&
                       (state != 25U) && (state != 3U) && (state != 17U);
      if (toyota_aol_lta) {
        const unsigned int lta_state = (msg->data[1] >> 3U) & 0x1FU;
        toyota_aol_eps = toyota_aol_eps && (lta_state != 0U) && (lta_state != 9U) && (lta_state != 11U) && (lta_state != 21U) &&
                          (lta_state != 25U) && (lta_state != 3U) && (lta_state != 17U);
      }
    } else {
    }
    if (index < 4U) {
      toyota_aol_seen[index] = true;
      toyota_aol_ts[index] = microsecond_timer_get();
    }
  } else {
  }
}

static void toyota_aol_configure(uint16_t param) {
  toyota_aol_reset();
  toyota_camera_2aa_ambiguous = false;
  toyota_prius_sdsu_ambiguous = false;
  toyota_eps8_sdsu = (param == 0x8049U) || (param == 0x8249U) || (param == 0x8449U) || (param == 0x8649U);
  toyota_legacy_sdsu = (param == 0x9158U) || (param == 0x9358U) || (param == 0x9149U) || (param == 0x9349U) || (param == 0x9164U) || (param == 0x9364U) || (param == 0xd149U) || (param == 0xd349U) || (param == 0xd04dU) || (param == 0xd24dU);
  toyota_alt_cruise = (param == 0x424DU) || ((toyota_legacy_sdsu || toyota_legacy_advert_param(param)) && ((param & 0x4000U) != 0U));
  toyota_aol_lta = (param == 0x449U) || (param == 0x649U) || (param == 0x1449U) || (param == 0x1649U) || (param == 0x8449U) || (param == 0x8649U);
  toyota_pedal = (param == 0x2049U) || (param == 0x2249U);
  toyota_aol_rav4h_filter = (param == 0x9049U) || (param == 0x9249U);
  toyota_sdsu_status = toyota_aol_rav4h_filter || toyota_eps8_sdsu || toyota_legacy_sdsu || toyota_prius_sdsu_param(param);
  toyota_aol_stock = (param == 585U) || (param == 4681U) || (param == 0x9249U) || (param == 0x2249U) || (param == 0x424DU) || (param == 0x649U) || (param == 0x1649U) || (param == 0x8249U) || (param == 0x8649U) || ((toyota_legacy_sdsu || toyota_legacy_advert_param(param) || toyota_camera_2aa_param(param) || toyota_prius_sdsu_param(param)) && ((param & 0x200U) != 0U));
#ifdef ALLOW_DEBUG
  toyota_aol_secoc = (param == 2121U);
#else
  toyota_aol_secoc = false;
#endif
  toyota_aol_enabled = ((toyota_eps8_sdsu || toyota_legacy_sdsu || toyota_legacy_advert_param(param) || toyota_camera_2aa_param(param) || toyota_prius_sdsu_param(param)) && (alternative_experience == 32)) || (toyota_aol_lta && (alternative_experience == 32)) || (toyota_aol_stock && (alternative_experience == 32)) ||
#ifdef ALLOW_DEBUG
                       (toyota_aol_secoc && (alternative_experience == 32)) ||
#endif
                       ((param == 0x9049U) && ((alternative_experience == 32) || (alternative_experience == 160))) ||
                       ((param == 0x2049U) && (alternative_experience == 32)) ||
                       ((param == 4169U) && (alternative_experience == 32)) ||
                       ((param == 73U) && ((alternative_experience == 32) || (alternative_experience == 160) || (alternative_experience == 288)));
  if (toyota_aol_enabled) {
    static const AolSafetyPolicy policy = {
      .reset = toyota_aol_reset,
      .request_mask = toyota_aol_request,
      .permission_mask = toyota_aol_permission,
      .rx_invalid = toyota_aol_reset,
    };
    aol_policy = &policy;
  }
}
