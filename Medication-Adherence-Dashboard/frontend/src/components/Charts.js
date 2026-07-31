import React, { useEffect, useRef } from 'react';
import * as am5 from '@amcharts/amcharts5';
import * as am5percent from '@amcharts/amcharts5/percent';
import * as am5xy from '@amcharts/amcharts5/xy';
import am5themes_Animated from '@amcharts/amcharts5/themes/Animated';
import './Charts.css';

// Default KPIs so charts always render (no blank dashboard when data is missing or API fails)
const DEFAULT_KPIS = {
  low_count: 0,
  med_count: 0,
  high_count: 0,
  interventions_30d: 0,
  interventions_7d: 0,
  notified_unique: 0,
  responded_unique: 0,
  notified_today: 0,
};

function Charts({ trendData, data }) {
  const donutChartRef = useRef(null);
  const barChartRef = useRef(null);
  const donutRootRef = useRef(null);
  const barRootRef = useRef(null);
  const kpis = (data && data.kpis) ? data.kpis : DEFAULT_KPIS;

  // Donut Chart Effect
  useEffect(() => {
    if (donutChartRef.current && !donutRootRef.current) {
      try {
      // Create root element
      let root = am5.Root.new(donutChartRef.current);
      if (!root || !root.container) return;

      // Skip setThemes - Animated theme can cause "Cannot read properties of undefined (reading 'set')" in some amCharts/builds

      try {
        if (root.licenseRoot && typeof root.licenseRoot.set === "function") {
          root.licenseRoot.set("background", am5.color("#00000000"));
          root.licenseRoot.set("opacity", 0);
        }
      } catch (_) {}

      try { if (root.fontFamily !== undefined) root.fontFamily = "system-ui, sans-serif"; } catch (_) {}

      // Create chart - do not pass layout/verticalLayout to avoid amCharts internal .set(undefined)
      let chart = root.container.children.push(am5percent.PieChart.new(root, {
        radius: am5.percent(90),
        innerRadius: am5.percent(50)
      }));
      if (!chart || !chart.series) return;

      // Prepare data with color field - Low (dark red), Medium (dark amber), High (dark green). Use kpis (has DEFAULT_KPIS fallback).
      const donutData = [
        { category: 'Low', value: kpis.low_count || 0, color: am5.color('#991B1B') },
        { category: 'Medium', value: kpis.med_count || 0, color: am5.color('#B45309') },
        { category: 'High', value: kpis.high_count || 0, color: am5.color('#065F46') }
      ];

      // Create series
      let series = chart.series.push(am5percent.PieSeries.new(root, {
        name: "Series",
        valueField: "value",
        categoryField: "category"
      }));
      if (!series) return;

      // Set color field to use colors from data (guard template)
      if (series.slices && series.slices.template && typeof series.slices.template.set === "function") {
        series.slices.template.set("propertyFields", { fill: "color" });
      }
      if (series.data && typeof series.data.setAll === "function") {
        series.data.setAll(donutData);
      }

      // Disabling labels and ticks (guard - some amCharts builds have undefined labels/ticks)
      if (series.labels && series.labels.template && typeof series.labels.template.set === "function") {
        series.labels.template.set("visible", false);
      }
      if (series.ticks && series.ticks.template && typeof series.ticks.template.set === "function") {
        series.ticks.template.set("visible", false);
      }

      // Adding solid glossy gradients with enhanced contrast for dark shades
      if (series.slices && series.slices.template) {
        if (typeof series.slices.template.set === "function") series.slices.template.set("strokeOpacity", 0);
        if (typeof series.slices.template.adapters !== "undefined" && typeof series.slices.template.adapters.add === "function") {
          series.slices.template.adapters.add("fillGradient", function(fillGradient, target) {
        if (target.dataItem && target.dataItem.dataContext) {
          const baseColor = target.dataItem.dataContext.color;
          if (baseColor) {
            return am5.RadialGradient.new(root, {
              stops: [{
                color: baseColor,
                brighten: 0.4,
                opacity: 1
              }, {
                color: baseColor,
                brighten: 0.15,
                opacity: 1
              }, {
                color: baseColor,
                brighten: -0.15,
                opacity: 1
              }, {
                color: baseColor,
                brighten: -0.3,
                opacity: 1
              }]
            });
          }
        }
        return am5.RadialGradient.new(root, {
          stops: [{
            brighten: 0.3,
            opacity: 1
          }, {
            brighten: 0.1,
            opacity: 1
          }, {
            brighten: -0.1,
            opacity: 1
          }, {
            brighten: -0.2,
            opacity: 1
          }]
        });
          });
        }
      }

      // Create legend - no layout prop to avoid .set on undefined inside amCharts
      let legend = chart.children.push(am5.Legend.new(root, {
        centerY: am5.percent(50),
        y: am5.percent(50)
      }));
      if (legend) {
        if (legend.labels && legend.labels.template && typeof legend.labels.template.setAll === "function") {
          legend.labels.template.setAll({ 
            maxWidth: 100,
            width: 100,
            oversizedBehavior: "wrap",
            fontSize: 11,
            fontWeight: "500",
            fill: am5.color("#1E293B")
          });
        }
        if (legend.valueLabels && legend.valueLabels.template && typeof legend.valueLabels.template.setAll === "function") {
          legend.valueLabels.template.setAll({ 
            textAlign: "right",
            fontSize: 11,
            fontWeight: "600",
            fill: am5.color("#475569")
          });
        }
        if (legend.data && typeof legend.data.setAll === "function" && series.dataItems) {
          legend.data.setAll(series.dataItems);
        }
      }

      try { if (typeof series.appear === "function") series.appear(1000, 100); } catch (_) {}
      donutRootRef.current = root;
      } catch (err) {
        console.error("Donut chart init error:", err);
      }
    }

    // Cleanup function
    return () => {
      if (donutRootRef.current) {
        try { donutRootRef.current.dispose(); } catch (_) {}
        donutRootRef.current = null;
      }
    };
  }, [kpis]);

  // Bar Chart Effect - render with kpis (defaults when data missing) so bar chart is never blank
  useEffect(() => {
    if (barChartRef.current && !barRootRef.current) {
      try {
      // Create root element
      let root = am5.Root.new(barChartRef.current);
      if (!root || !root.container) return;

      // Skip setThemes to avoid .set on undefined in some amCharts builds
      try {
        if (root.licenseRoot && typeof root.licenseRoot.set === "function") {
          root.licenseRoot.set("background", am5.color("#00000000"));
          root.licenseRoot.set("opacity", 0);
        }
      } catch (_) {}
      try { if (root.fontFamily !== undefined) root.fontFamily = "system-ui, sans-serif"; } catch (_) {}

      // Create chart
      let chart = root.container.children.push(am5xy.XYChart.new(root, {
        panX: false,
        panY: false,
        wheelX: "none",
        wheelY: "none",
        paddingLeft: 0,
        paddingRight: 0
      }));

      // Create axes
      let yAxis = chart.yAxes.push(am5xy.ValueAxis.new(root, {
        renderer: am5xy.AxisRendererY.new(root, {
          strokeOpacity: 0.1,
          stroke: am5.color("#64748B")
        }),
        min: 0
      }));

      let xAxis = chart.xAxes.push(am5xy.CategoryAxis.new(root, {
        categoryField: "category",
        renderer: am5xy.AxisRendererX.new(root, {
          cellStartLocation: 0.1,
          cellEndLocation: 0.9,
          strokeOpacity: 0.1,
          stroke: am5.color("#64748B")
        })
      }));

      const xRenderer = xAxis && typeof xAxis.get === "function" ? xAxis.get("renderer") : null;
      if (xRenderer && xRenderer.labels && xRenderer.labels.template && typeof xRenderer.labels.template.setAll === "function") {
        xRenderer.labels.template.setAll({
          fontSize: 11,
          fontWeight: "500",
          fill: am5.color("#475569"),
          paddingTop: 5
        });
      }
      const yRenderer = yAxis && typeof yAxis.get === "function" ? yAxis.get("renderer") : null;
      if (yRenderer && yRenderer.labels && yRenderer.labels.template && typeof yRenderer.labels.template.setAll === "function") {
        yRenderer.labels.template.setAll({
          fontSize: 10,
          fontWeight: "500",
          fill: am5.color("#64748B")
        });
      }

      // Prepare data with dark shade colors (use kpis so bar chart works with default/empty data)
      const barData = [
        {
          category: "Interventions",
          value: kpis.interventions_30d || 0,
          color: am5.color("#4338CA")
        },
        {
          category: "Last 7 Days",
          value: kpis.interventions_7d || 0,
          color: am5.color("#6D28D9")
        },
        {
          category: "Notified",
          value: kpis.notified_unique || 0,
          color: am5.color("#1D4ED8")
        },
        {
          category: "Responded",
          value: kpis.responded_unique || 0,
          color: am5.color("#047857")
        },
        {
          category: "Today",
          value: kpis.notified_today || 0,
          color: am5.color("#B45309")
        }
      ];

      if (xAxis.data && typeof xAxis.data.setAll === "function") xAxis.data.setAll(barData);

      // Create series
      let series = chart.series.push(am5xy.ColumnSeries.new(root, {
        name: "Interventions",
        xAxis: xAxis,
        yAxis: yAxis,
        valueYField: "value",
        categoryXField: "category"
      }));
      if (!series) return;

      // Set colors from data (guard template)
      if (series.columns && series.columns.template && typeof series.columns.template.set === "function") {
        series.columns.template.set("propertyFields", { fill: "color" });
      }
      if (series.columns && series.columns.template && series.columns.template.adapters && typeof series.columns.template.adapters.add === "function") {
        series.columns.template.adapters.add("fillGradient", function(fillGradient, target) {
        if (target.dataItem && target.dataItem.dataContext) {
          const baseColor = target.dataItem.dataContext.color;
          if (baseColor) {
            return am5.LinearGradient.new(root, {
              stops: [
                { color: baseColor, opacity: 1, brighten: 0.3 },
                { color: baseColor, opacity: 1 },
                { color: baseColor, opacity: 1, brighten: -0.3 }
              ],
              rotation: 90
            });
          }
        }
        return fillGradient;
        });
      }

      if (series.columns && series.columns.template) {
        if (typeof series.columns.template.setAll === "function") {
          series.columns.template.setAll({
            cornerRadiusTL: 6,
            cornerRadiusTR: 6,
            strokeOpacity: 0,
            tooltipText: "{category}: {value}",
            tooltipY: 0
          });
        }
        if (series.columns.template.states && typeof series.columns.template.states.create === "function") {
          series.columns.template.states.create("hover", {
            fillGradient: am5.LinearGradient.new(root, {
              stops: [
                { color: am5.color("#FFFFFF"), opacity: 0.3 },
                { color: am5.color("#FFFFFF"), opacity: 0 }
              ],
              rotation: 90
            })
          });
        }
      }

      if (series.bullets && typeof series.bullets.push === "function") {
        series.bullets.push(function() {
          return am5.Bullet.new(root, {
            locationY: 1,
            sprite: am5.Label.new(root, {
              text: "{value}",
              fill: am5.color("#1E293B"),
              centerY: 0,
              centerX: am5.percent(50),
              populateText: true,
              fontSize: 11,
              fontWeight: "600"
            })
          });
        });
      }

      if (series.data && typeof series.data.setAll === "function") series.data.setAll(barData);

      if (chart && typeof chart.set === "function") {
        const cursor = am5xy.XYCursor && am5xy.XYCursor.new ? am5xy.XYCursor.new(root, { behavior: "none" }) : null;
        if (cursor) chart.set("cursor", cursor);
      }

      try { if (typeof series.appear === "function") series.appear(1000, 100); } catch (_) {}
      barRootRef.current = root;
      } catch (err) {
        console.error("Bar chart init error:", err);
      }
    }

    // Cleanup function
    return () => {
      if (barRootRef.current) {
        try { barRootRef.current.dispose(); } catch (_) {}
        barRootRef.current = null;
      }
    };
  }, [kpis]);

  // Always render charts (with DEFAULT_KPIS when data is missing) so dashboard is never blank
  return (
    <div className="charts-container">
      <div className="chart-card card chart-3d">
        <div className="chart-header">
          <h3 className="card-title">📊 Adherence Distribution</h3>
          <div className="chart-info-badge">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M2 17L12 22L22 17" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M2 12L12 17L22 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            <span>Real-time Data</span>
          </div>
        </div>
        <div className="donut-chart" ref={donutChartRef} style={{ width: '100%', height: '200px' }}></div>
      </div>
      
      <div className="chart-card card chart-3d">
        <div className="chart-header">
          <h3 className="card-title">📈 Intervention Metrics</h3>
          <div className="chart-info-badge">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M3 3v18h18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M18 7l-5-5-5 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M7 21l5-5 5 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            <span>Performance</span>
          </div>
        </div>
        <div className="bar-chart" ref={barChartRef} style={{ width: '100%', height: '200px' }}></div>
      </div>
    </div>
  );
}

export default Charts;
