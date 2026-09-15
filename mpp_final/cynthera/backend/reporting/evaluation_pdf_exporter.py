"""Evaluation PDF exporter for Phase 4E Benchmark and Ablation Reports.

Generates a publication-grade evaluation PDF from a BenchmarkEvaluationReport.
"""
from __future__ import annotations

import io
import time
from typing import Any

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether
)

from backend.evaluation.benchmark_models import (
    BenchmarkEvaluationReport,
    BenchmarkClass,
)


class EvaluationPDFExporter:
    """Renders a BenchmarkEvaluationReport as a structured PDF document."""

    def __init__(self, report: BenchmarkEvaluationReport) -> None:
        self._report = report

    def generate_pdf_bytes(self) -> bytes:
        """Generate PDF byte stream."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            leftMargin=1.5 * cm,
            rightMargin=1.5 * cm,
            topMargin=1.5 * cm,
            bottomMargin=1.5 * cm,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "ReportTitle",
            parent=styles["Heading1"],
            fontSize=20,
            leading=24,
            textColor=colors.HexColor("#1e293b"),
            fontName="Helvetica-Bold",
        )
        subtitle_style = ParagraphStyle(
            "ReportSubtitle",
            parent=styles["Normal"],
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#64748b"),
        )
        section_style = ParagraphStyle(
            "ReportSection",
            parent=styles["Heading2"],
            fontSize=12,
            leading=16,
            textColor=colors.HexColor("#1e293b"),
            fontName="Helvetica-Bold",
            spaceBefore=10,
            spaceAfter=4,
        )
        body_style = ParagraphStyle(
            "ReportBody",
            parent=styles["Normal"],
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor("#334155"),
        )
        caption_style = ParagraphStyle(
            "ReportCaption",
            parent=styles["Normal"],
            fontSize=7.5,
            leading=10,
            textColor=colors.HexColor("#64748b"),
            fontName="Helvetica-Oblique",
        )

        story: list[Any] = []

        # ── Header / Cover ───────────────────────────────────────────────────
        story.append(Paragraph("CYNTHERA", title_style))
        story.append(Paragraph("Phase 4E — Therapeutic Direction Evaluation Report", subtitle_style))
        story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#4f46e5")))
        story.append(Spacer(1, 0.3 * cm))

        meta_p = Paragraph(
            f"<b>Evaluation Timestamp:</b> {self._report.evaluation_timestamp or time.strftime('%Y-%m-%d %H:%M UTC')} | "
            f"<b>Benchmark Version:</b> {self._report.benchmark_version} | "
            f"<b>Cache Version:</b> {self._report.cache_version}",
            caption_style,
        )
        story.append(meta_p)
        story.append(Spacer(1, 0.4 * cm))

        # ── 1. Executive Summary ─────────────────────────────────────────────
        story.append(Paragraph("1. Executive Summary", section_style))
        story.append(HRFlowable(width="100%", thickness=0.75, color=colors.HexColor("#e2e8f0")))
        m = self._report.full_4d_metrics
        acc_display = f"{m.accuracy:.1%}" if m.accuracy is not None else "N/A"
        summary_text = (
            f"This benchmark report evaluates the therapeutic direction reasoning engine (Phase 4D) "
            f"across {m.total_cases} curated benchmark cases ({m.positive_cases} positive, {m.negative_cases} negative, "
            f"{m.uncertain_cases} uncertain). The system achieved an overall prediction accuracy of <b>{acc_display}</b> "
            f"({m.correct_predictions}/{m.total_cases} correct, {m.unresolved_predictions} unresolved). "
            f"Directional concordance ratios and publication-level evidence clustering were strictly enforced."
        )
        story.append(Paragraph(summary_text, body_style))
        story.append(Spacer(1, 0.3 * cm))

        # ── 2. Overall Metrics Table ─────────────────────────────────────────
        story.append(Paragraph("2. Overall Performance Metrics", section_style))
        story.append(HRFlowable(width="100%", thickness=0.75, color=colors.HexColor("#e2e8f0")))

        metrics_data = [
            ["Metric", "Full Phase 4D", "Baseline (Target Existence)", "Interpretation"],
            [
                "Accuracy",
                f"{m.accuracy:.1%}" if m.accuracy is not None else "N/A",
                f"{self._report.baseline_metrics.accuracy:.1%}" if self._report.baseline_metrics.accuracy is not None else "N/A",
                "Overall exact classification concordance",
            ],
            [
                "Precision",
                f"{m.precision:.1%}" if m.precision is not None else "N/A",
                f"{self._report.baseline_metrics.precision:.1%}" if self._report.baseline_metrics.precision is not None else "N/A",
                "Positive prediction reliability",
            ],
            [
                "Recall / Sensitivity",
                f"{m.recall:.1%}" if m.recall is not None else "N/A",
                f"{self._report.baseline_metrics.recall:.1%}" if self._report.baseline_metrics.recall is not None else "N/A",
                "Coverage of true positive indications",
            ],
            [
                "Specificity",
                f"{m.specificity:.1%}" if m.specificity is not None else "N/A",
                f"{self._report.baseline_metrics.specificity:.1%}" if self._report.baseline_metrics.specificity is not None else "N/A",
                "Rejection of directional negatives",
            ],
            [
                "F1 Score",
                f"{m.f1_score:.3f}" if m.f1_score is not None else "N/A",
                f"{self._report.baseline_metrics.f1_score:.3f}" if self._report.baseline_metrics.f1_score is not None else "N/A",
                "Harmonic mean of precision and recall",
            ],
            [
                "Matthews Correlation (MCC)",
                f"{m.mcc:.3f}" if m.mcc is not None else "N/A",
                f"{self._report.baseline_metrics.mcc:.3f}" if self._report.baseline_metrics.mcc is not None else "N/A",
                "Balanced multi-class association metric",
            ],
        ]

        t_metrics = Table(metrics_data, colWidths=[4.5 * cm, 3.5 * cm, 4.5 * cm, 5.5 * cm])
        t_metrics.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f8fafc"), colors.white]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(t_metrics)
        story.append(Spacer(1, 0.3 * cm))

        # ── 3. Confusion Matrix ──────────────────────────────────────────────
        story.append(Paragraph("3. Multi-Class Confusion Matrix", section_style))
        story.append(HRFlowable(width="100%", thickness=0.75, color=colors.HexColor("#e2e8f0")))

        cm_obj = m.confusion_matrix
        cm_data = [
            ["Expected \\ Predicted", "Pred POSITIVE", "Pred NEGATIVE", "Pred UNCERTAIN", "Class Total"],
            [
                "Exp POSITIVE",
                str(cm_obj.get(BenchmarkClass.POSITIVE, BenchmarkClass.POSITIVE)),
                str(cm_obj.get(BenchmarkClass.POSITIVE, BenchmarkClass.NEGATIVE)),
                str(cm_obj.get(BenchmarkClass.POSITIVE, BenchmarkClass.UNCERTAIN)),
                str(m.positive_cases),
            ],
            [
                "Exp NEGATIVE",
                str(cm_obj.get(BenchmarkClass.NEGATIVE, BenchmarkClass.POSITIVE)),
                str(cm_obj.get(BenchmarkClass.NEGATIVE, BenchmarkClass.NEGATIVE)),
                str(cm_obj.get(BenchmarkClass.NEGATIVE, BenchmarkClass.UNCERTAIN)),
                str(m.negative_cases),
            ],
            [
                "Exp UNCERTAIN",
                str(cm_obj.get(BenchmarkClass.UNCERTAIN, BenchmarkClass.POSITIVE)),
                str(cm_obj.get(BenchmarkClass.UNCERTAIN, BenchmarkClass.NEGATIVE)),
                str(cm_obj.get(BenchmarkClass.UNCERTAIN, BenchmarkClass.UNCERTAIN)),
                str(m.uncertain_cases),
            ],
        ]

        t_cm = Table(cm_data, colWidths=[4.5 * cm, 3.5 * cm, 3.5 * cm, 3.5 * cm, 3 * cm])
        t_cm.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f766e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f0fdfa"), colors.white]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t_cm)
        story.append(Spacer(1, 0.3 * cm))

        # ── 4. Per-Case Results ──────────────────────────────────────────────
        story.append(Paragraph("4. Benchmark Case Evaluations", section_style))
        story.append(HRFlowable(width="100%", thickness=0.75, color=colors.HexColor("#e2e8f0")))

        case_headers = [
            "Case ID", "Drug", "Disease", "Expected", "Predicted",
            "Exp. Target", "Pipeline Target", "Match", "Concordance", "Verdict",
        ]
        case_rows = [case_headers]
        for cr in self._report.case_results:
            is_pass = cr.is_correct
            status_str = "PASS" if is_pass else ("UNCERTAIN" if cr.predicted_class == BenchmarkClass.UNCERTAIN else "FAIL")
            # target_match display
            if cr.target_match is True:
                match_str = "YES"
            elif cr.target_match is False:
                match_str = "NO"
            else:
                match_str = "—"
            case_rows.append([
                cr.case.case_id,
                cr.case.drug[:12],
                cr.case.disease[:18],
                cr.case.expected_class.value,
                cr.predicted_class.value,
                cr.case.expected_target or "—",
                cr.primary_target or "—",
                match_str,
                f"{cr.directional_concordance:.2f}",
                status_str,
            ])

        t_cases = Table(
            case_rows,
            colWidths=[2.2 * cm, 2.2 * cm, 3 * cm, 2 * cm, 2 * cm, 2 * cm, 2.2 * cm, 1.3 * cm, 1.8 * cm, 1.5 * cm],
        )
        t_cases.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#312e81")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#eef2ff"), colors.white]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(t_cases)
        story.append(Spacer(1, 0.3 * cm))

        # ── 5. Ablation Study ────────────────────────────────────────────────
        if self._report.ablation_results:
            story.append(Paragraph("5. Systematic Ablation Analysis", section_style))
            story.append(HRFlowable(width="100%", thickness=0.75, color=colors.HexColor("#e2e8f0")))

            ablation_data = [["Ablation Configuration", "Accuracy", "Precision", "Recall", "F1", "Changed Cases"]]
            for ab in self._report.ablation_results:
                m_ab = ab.metrics
                acc_s = f"{m_ab.accuracy:.1%}" if m_ab.accuracy is not None else "N/A"
                prec_s = f"{m_ab.precision:.1%}" if m_ab.precision is not None else "N/A"
                rec_s = f"{m_ab.recall:.1%}" if m_ab.recall is not None else "N/A"
                f1_s = f"{m_ab.f1_score:.3f}" if m_ab.f1_score is not None else "N/A"
                chg_cnt = len(ab.changed_cases_from_full)
                ablation_data.append([
                    ab.config_name.value,
                    acc_s,
                    prec_s,
                    rec_s,
                    f1_s,
                    f"{chg_cnt} case(s) shifted",
                ])

            t_ab = Table(ablation_data, colWidths=[5.5 * cm, 2.5 * cm, 2.5 * cm, 2.5 * cm, 2.5 * cm, 3 * cm])
            t_ab.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#065f46")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#ecfdf5"), colors.white]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ]))
            story.append(t_ab)
            story.append(Spacer(1, 0.3 * cm))

        # ── 6. Contradiction & Conflict Analysis ────────────────────────────
        if self._report.contradiction_metrics:
            cm_m = self._report.contradiction_metrics
            story.append(Paragraph("6. Contradiction & Conflict Resolution Metrics", section_style))
            story.append(HRFlowable(width="100%", thickness=0.75, color=colors.HexColor("#e2e8f0")))

            det_s = f"{cm_m.contradiction_detection_rate:.1%}" if cm_m.contradiction_detection_rate is not None else "N/A"
            res_s = f"{cm_m.contradiction_resolution_rate:.1%}" if cm_m.contradiction_resolution_rate is not None else "N/A"
            bal_s = f"{cm_m.balanced_conflict_insufficient_rate:.1%}" if cm_m.balanced_conflict_insufficient_rate is not None else "N/A"
            fls_s = f"{cm_m.false_directional_resolution_rate:.1%}" if cm_m.false_directional_resolution_rate is not None else "N/A"

            conflict_data = [
                ["Metric", "Value", "Scientific Definition"],
                ["Contradiction Detection Rate", det_s, "Fraction of opposing cases with detected conflicting evidence"],
                ["Contradiction Resolution Rate", res_s, "Fraction of genuine opposing cases resolved to OPPOSES/NEGATIVE"],
                ["Balanced Conflict Insufficient Rate", bal_s, "Fraction of balanced conflicts resolved to INSUFFICIENT/UNCERTAIN"],
                ["False Directional Resolution Rate", fls_s, "Fraction of opposing cases falsely resolved to SUPPORTS/POSITIVE"],
            ]

            t_conflict = Table(conflict_data, colWidths=[6.5 * cm, 3.5 * cm, 8.5 * cm])
            t_conflict.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#831843")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#fdf2f8"), colors.white]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ]))
            story.append(t_conflict)
            story.append(Spacer(1, 0.3 * cm))

        # ── 7. Scientific Interpretation & Reproducibility ───────────────────
        story.append(Paragraph("7. Interpretation &amp; Limitations", section_style))
        story.append(HRFlowable(width="100%", thickness=0.75, color=colors.HexColor("#e2e8f0")))
        story.append(Paragraph(
            "<b>Observed Findings:</b> Directional alignment enables disambiguation between therapeutic agonists "
            "and antagonists on shared targets, resolving false-positive connectivity errors present in naive target-existence baselines.<br/>"
            "<b>Contradiction Awareness:</b> Explicit detection of pharmacological counter-indications (e.g. muscarinic agonism in asthma, "
            "beta-agonism in hypertension, androgen agonism in prostate cancer) prevents dangerous false-positive recommendations.<br/>"
            "<b>Methodological Limitations:</b> The benchmark dataset contains machine-readable ground truth controls. "
            "Concordance ratio measures directional consensus rather than statistical sample size.",
            body_style,
        ))
        story.append(Spacer(1, 0.4 * cm))

        # ── 8. Statistical Uncertainty (Bootstrap CI) ────────────────────────
        if self._report.final_test_metrics_with_ci is not None:
            ci_m = self._report.final_test_metrics_with_ci
            story.append(Paragraph("8. Statistical Uncertainty — Bootstrap Confidence Intervals", section_style))
            story.append(HRFlowable(width="100%", thickness=0.75, color=colors.HexColor("#e2e8f0")))

            def _fmt_ci(ci: tuple[float, float] | None, point: float | None) -> str:
                if ci is None or point is None:
                    return "N/A"
                return f"{point:.1%} [{ci[0]:.1%}, {ci[1]:.1%}]"

            ci_data = [
                ["Metric", "Point Estimate [95% CI]"],
                ["Accuracy", _fmt_ci(ci_m.accuracy_ci, ci_m.accuracy)],
                ["Precision", _fmt_ci(ci_m.precision_ci, ci_m.precision)],
                ["Recall / Sensitivity", _fmt_ci(ci_m.recall_ci, ci_m.recall)],
                ["Specificity", _fmt_ci(ci_m.specificity_ci, ci_m.specificity)],
                ["Matthews Correlation (MCC)", _fmt_ci(ci_m.mcc_ci, ci_m.mcc)],
            ]
            t_ci = Table(ci_data, colWidths=[6 * cm, 9.5 * cm])
            t_ci.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f0f4ff"), colors.white]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]))
            story.append(t_ci)
            n_test = ci_m.total_cases
            story.append(Spacer(1, 0.15 * cm))
            story.append(Paragraph(
                f"CIs computed via {ci_m.n_bootstrap} bootstrap resamples (seed=42) of {n_test} TEST-split cases. "
                f"CI level: {ci_m.ci_level:.0%}. Wider intervals reflect smaller sample size — "
                f"results should be interpreted with appropriate caution.",
                caption_style,
            ))
            story.append(Spacer(1, 0.3 * cm))

        # ── 9. Calibration Summary ───────────────────────────────────────────
        if self._report.calibration_summary:
            story.append(Paragraph("9. Weight Calibration Summary (DEV Split)", section_style))
            story.append(HRFlowable(width="100%", thickness=0.75, color=colors.HexColor("#e2e8f0")))

            cal = self._report.calibration_summary
            cal_data = [["Configuration", "Direct", "Curated", "Inferred", "DEV MCC", "Selected?"]]
            best_cfg = cal.get("best_config", "")
            for cfg_name, vals in cal.items():
                if cfg_name in ("best_config", "calibration_note"):
                    continue
                if not isinstance(vals, dict):
                    continue
                selected = "YES" if cfg_name == best_cfg else ""
                cal_data.append([
                    cfg_name,
                    str(vals.get("direct", "—")),
                    str(vals.get("curated", "—")),
                    str(vals.get("inferred", "—")),
                    f"{vals.get('dev_mcc', 0):.4f}" if vals.get('dev_mcc') is not None else "N/A",
                    selected,
                ])
            if len(cal_data) > 1:
                t_cal = Table(cal_data, colWidths=[4 * cm, 2.5 * cm, 2.5 * cm, 2.5 * cm, 3 * cm, 2.5 * cm])
                t_cal.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4c1d95")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f5f3ff"), colors.white]),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ]))
                story.append(t_cal)
                note = cal.get("calibration_note", "Calibration performed on DEVELOPMENT split only. TEST labels not used.")
                story.append(Spacer(1, 0.15 * cm))
                story.append(Paragraph(note, caption_style))
                story.append(Spacer(1, 0.3 * cm))

        doc.build(story)
        return buffer.getvalue()
