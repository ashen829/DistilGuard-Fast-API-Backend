"""
PDF Report Generator for FL Malicious Client Detection Reports

Generates user-friendly PDF reports with:
- Clear table format for easy reading
- Client detection summary
- SHAP feature analysis tables
- LLM explanations
- Professional formatting
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class PDFReportGenerator:
    """Generates PDF reports for malicious client detection"""
    
    @staticmethod
    def generate_pdf_report(
        session_id: str,
        round_number: int,
        reports: List[Dict[str, Any]],
        output_path: Optional[Path] = None
    ) -> Optional[Path]:
        """
        Generate a PDF report from malicious client detection data.
        
        Args:
            session_id: FL session ID
            round_number: Round number
            reports: List of report dictionaries with client_id, explanation, malicious_score
            output_path: Output directory path (default: ./reports/)
        
        Returns:
            Path to generated PDF file or None if generation fails
        """
        try:
            from reportlab.lib.pagesizes import letter, A4
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
            from reportlab.lib import colors
            from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
            
            # Set default output path
            if output_path is None:
                output_path = Path("./reports")
            output_path.mkdir(parents=True, exist_ok=True)
            
            # Create PDF filename
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            pdf_filename = f"fl_report_session_{session_id}_round_{round_number}_{timestamp}.pdf"
            pdf_path = output_path / pdf_filename
            
            logger.info(f"Generating PDF report: {pdf_path}")
            
            # Create PDF document
            doc = SimpleDocTemplate(
                str(pdf_path),
                pagesize=letter,
                topMargin=0.5*inch,
                bottomMargin=0.5*inch,
                leftMargin=0.5*inch,
                rightMargin=0.5*inch
            )
            
            # Container for PDF elements
            story = []
            
            # Get styles
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=16,
                textColor=colors.HexColor('#1a1a1a'),
                spaceAfter=12,
                alignment=TA_CENTER
            )
            
            heading_style = ParagraphStyle(
                'CustomHeading',
                parent=styles['Heading2'],
                fontSize=12,
                textColor=colors.HexColor('#2c3e50'),
                spaceAfter=8,
                spaceBefore=8
            )
            
            # Title
            title = Paragraph(
                "🔒 Federated Learning Malicious Client Detection Report",
                title_style
            )
            story.append(title)
            story.append(Spacer(1, 0.2*inch))
            
            # Report metadata
            metadata_data = [
                ["Session ID:", session_id],
                ["Round Number:", str(round_number)],
                ["Report Generated:", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")],
                ["Total Malicious Clients:", str(len(reports))]
            ]
            
            metadata_table = Table(metadata_data, colWidths=[2*inch, 4*inch])
            metadata_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#ecf0f1')),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#bdc3c7'))
            ]))
            story.append(metadata_table)
            story.append(Spacer(1, 0.3*inch))
            
            # Detailed analysis for each client
            story.append(Paragraph("Detailed Client Analysis", heading_style))
            
            for idx, report in enumerate(reports):
                # Add page break if needed
                if idx > 0:
                    story.append(PageBreak())
                
                client_id = report.get("client_id", "N/A")
                explanation = report.get("explanation", "No explanation available")
                malicious_score = report.get("malicious_score")
                
                # Client header
                client_title = f"Client {client_id} - Round {round_number}"
                story.append(Paragraph(client_title, heading_style))
                
                # Client details table
                client_details_data = [
                    ["Client ID:", str(client_id)],
                    ["Round Number:", str(round_number)]
                ]
                
                client_details_table = Table(client_details_data, colWidths=[1.5*inch, 4.5*inch])
                client_details_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#ecf0f1')),
                    ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                    ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                    ('ALIGN', (1, 0), (1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 9),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                    ('TOPPADDING', (0, 0), (-1, -1), 6),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#bdc3c7'))
                ]))
                story.append(client_details_table)
                story.append(Spacer(1, 0.15*inch))
                
                # Explanation section
                story.append(Paragraph("Detection Analysis", heading_style))
                
                explanation_style = ParagraphStyle(
                    'Explanation',
                    parent=styles['Normal'],
                    fontSize=9,
                    textColor=colors.HexColor('#2c3e50'),
                    spaceAfter=6
                )
                
                # Clean up explanation text
                cleaned_explanation = explanation.replace("\n", " ").replace("  ", " ")
                explanation_paragraph = Paragraph(cleaned_explanation, explanation_style)
                story.append(explanation_paragraph)
                story.append(Spacer(1, 0.2*inch))
            
            # Build PDF
            doc.build(story)
            
            logger.info(f"✅ PDF report generated successfully: {pdf_path}")
            return pdf_path
            
        except ImportError as e:
            logger.error(f"reportlab not installed: {e}. Install with: pip install reportlab")
            return None
        except Exception as e:
            logger.error(f"Error generating PDF report: {e}", exc_info=True)
            return None
    
    @staticmethod
    def generate_csv_report(
        session_id: str,
        round_number: int,
        reports: List[Dict[str, Any]],
        output_path: Optional[Path] = None
    ) -> Optional[Path]:
        """
        Generate a CSV report as alternative to PDF.
        
        Args:
            session_id: FL session ID
            round_number: Round number
            reports: List of report dictionaries
            output_path: Output directory path
        
        Returns:
            Path to generated CSV file or None if generation fails
        """
        try:
            import csv
            
            if output_path is None:
                output_path = Path("./reports")
            output_path.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            csv_filename = f"fl_report_session_{session_id}_round_{round_number}_{timestamp}.csv"
            csv_path = output_path / csv_filename
            
            logger.info(f"Generating CSV report: {csv_path}")
            
            with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['Client ID', 'Round Number', 'Malicious Score', 'Detection Status', 'Explanation']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                writer.writeheader()
                
                for report in reports:
                    client_id = report.get("client_id", "N/A")
                    malicious_score = report.get("malicious_score")
                    explanation = report.get("explanation", "").replace("\n", " ")
                    
                    status = "MALICIOUS" if malicious_score and malicious_score >= 0.5 else "SUSPICIOUS"
                    score_str = f"{malicious_score:.2%}" if malicious_score else "N/A"
                    
                    writer.writerow({
                        'Client ID': client_id,
                        'Round Number': round_number,
                        'Malicious Score': score_str,
                        'Detection Status': status,
                        'Explanation': explanation[:500]  # Truncate to 500 chars for CSV readability
                    })
            
            logger.info(f"✅ CSV report generated successfully: {csv_path}")
            return csv_path
            
        except Exception as e:
            logger.error(f"Error generating CSV report: {e}", exc_info=True)
            return None


def get_pdf_generator() -> PDFReportGenerator:
    """Get PDF report generator"""
    return PDFReportGenerator()
