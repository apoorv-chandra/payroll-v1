"""Salary slip PDF generator (ReportLab)."""
from __future__ import annotations

import io

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT

from ..utils import indian_fmt


def build_salary_slip_pdf(tenant: dict, employee: dict, item: dict, run: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "title",
        parent=styles["Heading1"],
        fontSize=16,
        alignment=TA_LEFT,
        textColor=colors.HexColor("#0A0A0A"),
    )
    sub = ParagraphStyle("sub", parent=styles["Normal"], fontSize=10, textColor=colors.HexColor("#737373"))
    label = ParagraphStyle("lab", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#737373"))
    val = ParagraphStyle("val", parent=styles["Normal"], fontSize=10, textColor=colors.HexColor("#0A0A0A"))

    story = []
    story.append(Paragraph(tenant["name"], title))
    if tenant.get("address"):
        story.append(Paragraph(tenant["address"], sub))
    story.append(Spacer(1, 6))
    months = ["", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    story.append(Paragraph(f"Salary Slip — {months[run['month']]} {run['year']}", styles["Heading2"]))
    story.append(Spacer(1, 8))

    info_data = [
        [Paragraph("Employee", label), Paragraph(employee["name"], val), Paragraph("Code", label), Paragraph(employee["emp_code"], val)],
        [Paragraph("Designation", label), Paragraph(employee.get("designation") or "-", val), Paragraph("Department", label), Paragraph(employee.get("department") or "-", val)],
        [Paragraph("Bank A/C", label), Paragraph(employee.get("bank_account") or "-", val), Paragraph("IFSC", label), Paragraph(employee.get("ifsc") or "-", val)],
    ]
    info = Table(info_data, colWidths=[28 * mm, 60 * mm, 28 * mm, 50 * mm])
    info.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#E5E7EB")),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#F3F4F6")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(info)
    story.append(Spacer(1, 12))

    rs = "Rs. "
    detail = [
        ["Description", "Days / Amount"],
        ["Monthly Salary (CTC)", f"{rs}{indian_fmt(item['monthly_salary'])}"],
        ["Working Days (basis)", str(run['working_days'])],
        ["Present Days", str(item['present_days'])],
        ["Paid Leave Days", str(item['paid_leave_days'])],
        ["Payable Days", str(item['payable_days'])],
        ["Per-Day Rate", f"{rs}{indian_fmt(item['per_day'])}"],
        ["Gross Salary", f"{rs}{indian_fmt(item['gross_salary'])}"],
        ["Deductions", f"{rs}{indian_fmt(item.get('deductions', 0))}"],
        ["Net Payable", f"{rs}{indian_fmt(item['net_salary'])}"],
    ]
    t = Table(detail, colWidths=[100 * mm, 66 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F9FAFB")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#737373")),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#E5E7EB")),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#F3F4F6")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#EFF6FF")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
    ]))
    story.append(t)
    story.append(Spacer(1, 10))
    if item.get("disbursement"):
        d = item["disbursement"]
        story.append(Paragraph(
            f"Disbursed via {d['method'].upper()} on {d['at'][:10]} — Txn: {d['txn_id']}",
            sub,
        ))
    story.append(Spacer(1, 16))
    story.append(Paragraph(
        "This is a system-generated salary slip and does not require a signature.",
        sub,
    ))
    doc.build(story)
    return buf.getvalue()
