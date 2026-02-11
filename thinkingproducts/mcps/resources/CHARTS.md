---
name: chart-visualization
description: Guidance for choosing chart types and understanding when to use each chart tool.
---

# Chart Types Guide

Use this guide to pick the right chart for the user’s data and intent. Focus on the chart type and when it’s appropriate.

## Chart Selection Guide

- **Time series & trends**:
  - `generate_line_chart`: trend over time or continuous x-axis.
  - `generate_area_chart`: accumulated or stacked trends over time.
  - `generate_dual_axes_chart`: two measures with different scales on the same x-axis.

- **Category comparisons**:
  - `generate_bar_chart`: horizontal comparison across categories.
  - `generate_column_chart`: vertical comparison across categories or time buckets.
  - `generate_histogram_chart`: frequency distribution for numeric samples.

- **Part-to-whole**:
  - `generate_pie_chart`: proportions of a whole.
  - `generate_treemap_chart`: hierarchical part-to-whole.

- **Relationships & overlap**:
  - `generate_scatter_chart`: correlation between two numeric variables.
  - `generate_sankey_chart`: flow between stages or nodes.
  - `generate_venn_chart`: overlap between sets.

- **Maps (China only)**:
  - `generate_district_map`: regions/administrative areas.
  - `generate_pin_map`: point locations (POIs).
  - `generate_path_map`: routes or paths between POIs.

- **Hierarchies & structures**:
  - `generate_organization_chart`: org structure or hierarchy.
  - `generate_mind_map`: topic tree or brainstorming map.

- **Specialized**:
  - `generate_radar_chart`: multi-dimensional comparison.
  - `generate_funnel_chart`: stage conversion/drop-off.
  - `generate_liquid_chart`: single percentage/progress.
  - `generate_word_cloud_chart`: text frequency/weight.
  - `generate_boxplot_chart`: distribution summary by category.
  - `generate_violin_chart`: distribution shape by category.
  - `generate_network_graph`: entity relationships with nodes/edges.
  - `generate_fishbone_diagram`: root-cause analysis.
  - `generate_flow_diagram`: process flow.
  - `generate_spreadsheet`: tables or pivot-style summaries.

## Notes
- Pick the simplest chart that matches the user’s goal and data shape.
- Prefer clarity: fewer series, concise labels, and readable scales.
