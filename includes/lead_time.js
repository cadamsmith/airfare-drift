// Shared lead-time (days-to-departure) bucketing for the booking curve.
//
// One definition, reused by int_daily_lead_stats (which builds the baseline) and
// later by the residual-anomaly model (which buckets an observation to look up
// its expectation). Keeping the CASE in one place guarantees the observation is
// scored against the bucket it was aggregated into — a divergence here would
// silently corrupt every z-score.
//
// Buckets are keyed by their integer lower bound (the join key); labelFromMin()
// renders the human range. Panel guarantees lead >= 14 (MIN_LEAD_DAYS); anything
// below that is out-of-scope and maps to NULL so it can be filtered, never
// mislabeled into the first bucket.

function bucketMin(col) {
  return `CASE
    WHEN ${col} < 14 THEN NULL
    WHEN ${col} < 21 THEN 14
    WHEN ${col} < 30 THEN 21
    WHEN ${col} < 45 THEN 30
    WHEN ${col} < 60 THEN 45
    WHEN ${col} < 90 THEN 60
    WHEN ${col} < 120 THEN 90
    WHEN ${col} < 180 THEN 120
    ELSE 180
  END`;
}

function labelFromMin(col) {
  return `CASE ${col}
    WHEN 14 THEN '14-20'
    WHEN 21 THEN '21-29'
    WHEN 30 THEN '30-44'
    WHEN 45 THEN '45-59'
    WHEN 60 THEN '60-89'
    WHEN 90 THEN '90-119'
    WHEN 120 THEN '120-179'
    WHEN 180 THEN '180+'
  END`;
}

module.exports = { bucketMin, labelFromMin };
