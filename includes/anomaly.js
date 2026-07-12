// Shared thresholds for the residual-anomaly layer, in one place so the baseline
// views and fct_fare_anomaly agree (and so the maturity gates are tunable from a
// single spot as data accumulates).
//
// The reliability gate counts DISTINCT ANCHORS (outbound_date), not raw
// observations: the panel re-observes each anchor every run, so N observations
// can be ~1 independent trip measured repeatedly. Gating on re-observation count
// would (a) grant false reliability to the most-re-observed (far) cells and
// (b) let loo_std collapse toward 2-day stability → spurious huge z. Distinct
// anchors is the honest independent-sample count; it is NOT additively
// recoverable from summed sufficient stats, so it's computed directly from the
// small int_trip_fares grain.

const MIN_RELIABLE_ANCHORS = 5;  // distinct anchors before a cell may drive a flag
const MIN_OBS_FOR_Z = 3;         // observations needed for a defined leave-one-out sample stddev
const MIN_ANCHORS_FOR_Z = 2;     // a z from a single anchor's 2-day self-variation is meaningless
const Z_THRESHOLD = 2.5;         // |z| at/above which a reliable cell flags an anomaly

module.exports = {
  MIN_RELIABLE_ANCHORS,
  MIN_OBS_FOR_Z,
  MIN_ANCHORS_FOR_Z,
  Z_THRESHOLD,
};
