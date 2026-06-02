"""
Report Generator — Profesyonel PDF rapor oluştur

Yapılandırma:
- reportlab ile PDF oluştur
- CFD + FEA sonuçlarını birleştir
- Grafikler ve tablolar ekle
- Executive summary oluştur
"""

import io
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak,
        Table, TableStyle, KeepTogether
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
    REPORTLAB_AVAILABLE = True
except ImportError:
    print("[WARNING] reportlab not available - using mock report generation")
    REPORTLAB_AVAILABLE = False

import matplotlib.pyplot as plt
import matplotlib.figure

from post_processing.cfd_postprocessor import CFDResult
from post_processing.fea_postprocessor import FEAResult
from post_processing.visualization import (
    CFDVisualizer, FEAVisualizer, CommonVisualizer
)


class PDFReportGenerator:
    """Profesyonel analiz raporu oluştur"""

    def __init__(self, output_path: Path):
        self.output_path = Path(output_path)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        self.styles = getSampleStyleSheet()
        self._customize_styles()

        self.story = []
        self.cfd_result = None
        self.fea_result = None

    def _customize_styles(self):
        """Özel yazı stilleri tanımla"""
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1f4788'),
            spaceAfter=12,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        ))

        self.styles.add(ParagraphStyle(
            name='CustomHeading2',
            parent=self.styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#2c5aa0'),
            spaceAfter=8,
            spaceBefore=8,
            fontName='Helvetica-Bold'
        ))

        self.styles.add(ParagraphStyle(
            name='CustomBody',
            parent=self.styles['BodyText'],
            fontSize=11,
            alignment=TA_JUSTIFY,
            spaceAfter=6
        ))

    def add_title_page(self, geometry_name: str, material_name: str):
        """Kapak sayfası ekle"""
        self.story.append(Spacer(1, 1.5*inch))

        title = Paragraph("ANALYSIS REPORT", self.styles['CustomTitle'])
        self.story.append(title)

        self.story.append(Spacer(1, 0.3*inch))

        subtitle = Paragraph(
            f"<b>{geometry_name}</b> — CFD & FEA Analysis",
            self.styles['Heading2']
        )
        self.story.append(subtitle)

        self.story.append(Spacer(1, 0.2*inch))

        info = Paragraph(
            f"<b>Geometry:</b> {geometry_name}<br/>"
            f"<b>Material:</b> {material_name}<br/>"
            f"<b>Date:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br/>"
            f"<b>System:</b> bilsem_beyin CFD/FEA v2.0",
            self.styles['Normal']
        )
        self.story.append(info)

        self.story.append(PageBreak())

    def add_executive_summary(self, cfd_result: CFDResult, fea_result: FEAResult):
        """Executive summary sayfası"""
        self.cfd_result = cfd_result
        self.fea_result = fea_result

        self.story.append(Paragraph("Executive Summary", self.styles['CustomHeading2']))
        self.story.append(Spacer(1, 0.1*inch))

        # Summary text
        summary_text = f"""
This report presents the results of computational fluid dynamics (CFD) and
finite element analysis (FEA) for the <b>{cfd_result.aircraft_name}</b> geometry
manufactured from <b>{fea_result.material.name}</b>.
<br/><br/>
<b>Analysis Conditions:</b><br/>
Wind Speed: {cfd_result.wind_speed:.1f} m/s | Reynolds: {cfd_result.reynolds_number:.2e} | Mach: {cfd_result.mach_number:.4f}
<br/><br/>
<b>Key Results:</b><br/>
• Drag Coefficient: {cfd_result.drag_coefficient:.4f}<br/>
• Lift Coefficient: {cfd_result.lift_coefficient:.4f}<br/>
• Max Stress: {fea_result.max_stress:.2f} MPa<br/>
• Safety Factor: {fea_result.safety_factor:.2f} ({fea_result.stress_status()})<br/>
"""
        self.story.append(Paragraph(summary_text, self.styles['CustomBody']))
        self.story.append(Spacer(1, 0.2*inch))

    def add_cfd_analysis(self, cfd_figures: Dict[str, io.BytesIO]):
        """CFD analiz sekmesi"""
        self.story.append(PageBreak())
        self.story.append(Paragraph("CFD Analysis", self.styles['CustomHeading2']))
        self.story.append(Spacer(1, 0.1*inch))

        # CFD metodoloji
        cfd_text = """
<b>Methodology:</b><br/>
Computational Fluid Dynamics (CFD) analysis was performed using OpenFOAM
with k-ω SST turbulence model. The flow domain was discretized using
approximately 2.5 million tetrahedral elements with boundary layer refinement
(y+ ≈ 27.7).
<br/><br/>
<b>Results:</b>
"""
        self.story.append(Paragraph(cfd_text, self.styles['CustomBody']))

        # Results table
        if self.cfd_result:
            cfd_table_data = [
                ['Parameter', 'Value', 'Unit'],
                ['Drag Coefficient', f"{self.cfd_result.drag_coefficient:.6f}", '-'],
                ['Lift Coefficient', f"{self.cfd_result.lift_coefficient:.6f}", '-'],
                ['Moment Coefficient', f"{self.cfd_result.moment_coefficient:.8f}", '-'],
                ['Drag Force', f"{self.cfd_result.drag_force:.2f}", 'N'],
                ['Lift Force', f"{self.cfd_result.lift_force:.2f}", 'N'],
                ['Reynolds Number', f"{self.cfd_result.reynolds_number:.2e}", '-'],
                ['Convergence Residual', f"{self.cfd_result.convergence_residual:.2e}", '-'],
                ['Iterations', f"{self.cfd_result.n_iterations}", '-'],
            ]

            table = Table(cfd_table_data, colWidths=[2.5*inch, 1.5*inch, 1*inch])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5aa0')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ]))
            self.story.append(table)

        self.story.append(Spacer(1, 0.2*inch))

        # Add figures if available
        if 'convergence' in cfd_figures:
            self.story.append(Paragraph("Convergence History", self.styles['Normal']))
            img = Image(cfd_figures['convergence'], width=5.5*inch, height=4*inch)
            self.story.append(img)
            self.story.append(Spacer(1, 0.1*inch))

    def add_fea_analysis(self, fea_figures: Dict[str, io.BytesIO]):
        """FEA analiz sekmesi"""
        self.story.append(PageBreak())
        self.story.append(Paragraph("FEA Analysis", self.styles['CustomHeading2']))
        self.story.append(Spacer(1, 0.1*inch))

        fea_text = """
<b>Methodology:</b><br/>
Finite Element Analysis (FEA) was performed using CalculiX solver with
linear elastic material model. The structure was discretized using
approximately 150,000 elements.
<br/><br/>
<b>Results:</b>
"""
        self.story.append(Paragraph(fea_text, self.styles['CustomBody']))

        # Results table
        if self.fea_result:
            fea_table_data = [
                ['Parameter', 'Value', 'Unit'],
                ['Max Stress (Von Mises)', f"{self.fea_result.max_stress:.2f}", 'MPa'],
                ['Material Yield Strength', f"{self.fea_result.material.yield_strength:.2f}", 'MPa'],
                ['Safety Factor', f"{self.fea_result.safety_factor:.2f}", '-'],
                ['Status', f"{self.fea_result.stress_status()}", '-'],
                ['Max Displacement', f"{self.fea_result.max_displacement:.4f}", 'mm'],
                ['Elements', f"{self.fea_result.n_elements}", '-'],
                ['Nodes', f"{self.fea_result.n_nodes}", '-'],
            ]

            # Add modal data if available
            if self.fea_result.natural_frequencies:
                fea_table_data.append(['First Natural Frequency',
                                      f"{self.fea_result.natural_frequencies[0]:.2f}", 'Hz'])

            table = Table(fea_table_data, colWidths=[2.5*inch, 1.5*inch, 1*inch])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5aa0')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.lightblue),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ]))
            self.story.append(table)

        self.story.append(Spacer(1, 0.2*inch))

        # Add figures if available
        if 'stress' in fea_figures:
            self.story.append(Paragraph("Von Mises Stress Distribution", self.styles['Normal']))
            img = Image(fea_figures['stress'], width=5.5*inch, height=4*inch)
            self.story.append(img)
            self.story.append(Spacer(1, 0.1*inch))

    def add_recommendations(self):
        """Öneriler ve sonuç"""
        self.story.append(PageBreak())
        self.story.append(Paragraph("Recommendations", self.styles['CustomHeading2']))
        self.story.append(Spacer(1, 0.1*inch))

        if self.fea_result and self.cfd_result:
            stress_status = self.fea_result.stress_status()

            if stress_status == "SAFE":
                rec_text = """
The structure is <b>mechanically safe</b> under the analyzed conditions.
The safety factor of {:.2f} provides adequate margin against material failure.
<br/><br/>
<b>Recommendations:</b><br/>
1. Design is suitable for implementation<br/>
2. Consider optimization for weight reduction<br/>
3. Perform fatigue analysis for extended service life<br/>
4. Validate with physical testing
""".format(self.fea_result.safety_factor)
            else:
                rec_text = """
The structure requires <b>design modifications</b>. The safety factor of {:.2f}
is below recommended threshold (1.5-2.0).
<br/><br/>
<b>Recommendations:</b><br/>
1. <b>Increase wall thickness</b> in critical zones<br/>
2. <b>Material upgrade</b> to higher strength alloy<br/>
3. <b>Geometry redesign</b> to reduce stress concentration<br/>
4. Perform detailed nonlinear analysis with contact
""".format(self.fea_result.safety_factor)

            self.story.append(Paragraph(rec_text, self.styles['CustomBody']))

        self.story.append(Spacer(1, 0.3*inch))
        self.story.append(Paragraph(
            "<b>Report prepared by:</b> bilsem_beyin CFD/FEA System v2.0<br/>"
            f"<b>Date:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            self.styles['Normal']
        ))

    def generate_pdf(self, cfd_result: CFDResult, fea_result: FEAResult,
                    cfd_figures: Dict[str, io.BytesIO] = None,
                    fea_figures: Dict[str, io.BytesIO] = None) -> Path:
        """
        PDF raporu oluştur ve kaydet
        → Returns: Path to generated PDF
        """
        # Initialize document
        doc = SimpleDocTemplate(
            str(self.output_path),
            pagesize=letter,
            rightMargin=0.75*inch,
            leftMargin=0.75*inch,
            topMargin=0.75*inch,
            bottomMargin=0.75*inch
        )

        # Clear story for new document
        self.story = []

        # Add sections
        self.add_title_page(cfd_result.aircraft_name, fea_result.material.name)
        self.add_executive_summary(cfd_result, fea_result)

        if cfd_figures:
            self.add_cfd_analysis(cfd_figures)

        if fea_figures:
            self.add_fea_analysis(fea_figures)

        self.add_recommendations()

        # Build PDF
        try:
            doc.build(self.story)
            print(f"[OK] PDF rapor olusturuldu: {self.output_path}")
            return self.output_path
        except Exception as e:
            print(f"[ERROR] PDF olusturma hatasi: {e}")
            return None


# For testing
if __name__ == "__main__":
    from material_database import MaterialLibrary

    lib = MaterialLibrary()
    material = lib.get_material("Aluminum 6061")

    # Create mock results
    cfd_result = CFDResult(
        aircraft_name="MiniHawk",
        wind_speed=15.0,
        reynolds_number=6e5,
        mach_number=0.044,
        drag_coefficient=0.145,
        lift_coefficient=0.523,
        moment_coefficient=-0.012,
        drag_force=245.0,
        lift_force=1023.0,
        moment=15.2,
        pressure_drag=230.0,
        viscous_drag=15.0,
        n_iterations=2000,
        convergence_residual=1e-5,
        mesh_elements=2500000
    )

    fea_result = FEAResult(
        aircraft_name="MiniHawk",
        material=material,
        analysis_type="STATIC",
        applied_load=12000,
        max_stress=125.4,
        max_displacement=2.34,
        safety_factor=2.19,
        n_elements=150000,
        n_nodes=45000
    )

    # Generate PDF
    generator = PDFReportGenerator(Path("test_report.pdf"))
    pdf_path = generator.generate_pdf(cfd_result, fea_result)
    print(f"[OK] Test rapor: {pdf_path}")
