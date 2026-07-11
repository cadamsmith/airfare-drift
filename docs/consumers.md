# Consumers: Looker Studio + ASP.NET Core app

Read this when **building the consumption layer** (build-order step 4, after the
warehouse produces real marts). Two consumption paths over the same marts, by design.

## Consumers (two modes of one warehouse, by design)

Deliberately two consumption paths over the same marts — framed as *range*, not duplication ("declarative-BI path vs. engineered-product path" is itself a talking point):

- **Looker Studio — the fast, zero-code BI path.** Built **first** (an early deliverable while the app is developed; also a "I know BI tools" signal). Native BQ connector, no app code: the single-route deep-dive (booking-curve heatmap, seasonality ribbon, residual-anomaly flags, event overlays). Keep it even after the app exists — it's a cheap win.
- **ASP.NET Core web app — the engineered-product path.** Retained for **portfolio breadth** (full-stack / .NET / EF Core), not because the product needs a second consumer. It is a **bespoke ATL–CMN analytical front-end (custom visualizations) + the OLTP state**, backed by a real serving layer. Built **last**, after the warehouse produces real marts (so charts render accumulated data, not empty axes), and scoped to the one route so it stays finishable — it's the single biggest chunk of work here.

**Where the .NET showcase actually is (be clear-eyed).** Interactive charts are rendered by a **JS charting lib** (Chart.js / Plotly / ECharts / D3) that .NET *serves* — the impressive-viz work is JS + data shaping. The **.NET** contribution is the **serving/query/caching layer** (controllers querying BQ via `Google.Cloud.BigQuery.V2`, shaping view models / JSON endpoints, Razor shell) plus the Postgres OLTP. (Pure server-rendered SVG with zero JS is possible but far less interactive — only if "no JS" is an explicit goal; default to a JS lib.)

**Serving layer — the committed answer to constraint #5 (previously the open "serving strategy").** The app must **never re-scan marts per page load**: it reads either a **cached BQ query (short TTL)** or a **small pre-computed serving table**. Building the viz forces this decision — a real OLAP-serving pattern worth showcasing.

**OLTP state (Postgres, via EF Core / Npgsql) — never written to BigQuery.** The single-route pivot killed "saved routes"; the genuine read/write state is **alert subscriptions + thresholds, an idempotent sent-alert log** (so it never re-alerts for the same regime), and **human-in-the-loop anomaly annotations** ("this spike was Eid / a data glitch") fed back as a labeled dataset. This is what honestly re-justifies the OLAP-vs-OLTP split on one route.
