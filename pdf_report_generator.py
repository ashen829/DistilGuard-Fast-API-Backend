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
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch
            from reportlab.platypus import (
                SimpleDocTemplate, Table, TableStyle, Paragraph, 
                Spacer, PageBreak
            )
            from reportlab.lib import colors
            from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
            from reportlab.platypus.flowables import HRFlowable
            
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
                topMargin=0.75*inch,
                bottomMargin=0.75*inch,
                leftMargin=0.75*inch,
                rightMargin=0.75*inch,
                title=f"FL Security Report - Session {session_id}"
            )
            
            # Container for PDF elements
            story = []
            
            # Get styles
            styles = getSampleStyleSheet()
            
            # Define custom styles
            title_style = ParagraphStyle(
                'MainTitle',
                parent=styles['Heading1'],
                fontSize=16,
                textColor=colors.HexColor('#1a365d'),
                spaceAfter=8,
                alignment=TA_CENTER,
                fontName='Helvetica-Bold'
            )
            
            subtitle_style = ParagraphStyle(
                'Subtitle',
                parent=styles['Normal'],
                fontSize=12,
                textColor=colors.HexColor('#4a5568'),
                spaceAfter=16,
                alignment=TA_CENTER,
                fontName='Helvetica'
            )
            
            section_style = ParagraphStyle(
                'SectionHeader',
                parent=styles['Heading2'],
                fontSize=14,
                textColor=colors.HexColor('#2d3748'),
                spaceAfter=6,
                spaceBefore=12,
                fontName='Helvetica-Bold'
            )
            
            client_header_style = ParagraphStyle(
                'ClientHeader',
                parent=styles['Heading3'],
                fontSize=13,
                textColor=colors.HexColor('#2b6cb0'),
                spaceAfter=4,
                spaceBefore=10,
                fontName='Helvetica-Bold'
            )
            
            explanation_style = ParagraphStyle(
                'ExplanationText',
                parent=styles['Normal'],
                fontSize=10,
                textColor=colors.HexColor('#4a5568'),
                spaceAfter=6,
                alignment=TA_JUSTIFY,
                leading=14,
                fontName='Helvetica'
            )
            
            footer_style = ParagraphStyle(
                'Footer',
                parent=styles['Normal'],
                fontSize=9,
                textColor=colors.HexColor('#718096'),
                alignment=TA_CENTER
            )
            
            # Title section
            story.append(Paragraph("Federated Learning Security Report", title_style))
            story.append(Paragraph("Malicious Client Detection Analysis", subtitle_style))
            story.append(Spacer(1, 0.2*inch))
            
            # Report Summary
            story.append(Paragraph("Report Summary", section_style))
            story.append(Spacer(1, 0.1*inch))
            
            # Metadata - using clean text instead of HTML
            current_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            status_text = f"{len(reports)} Malicious Client(s) Detected" if reports else "No Threats Detected"
            status_color = "#c53030" if reports else "#38a169"
            
            metadata_data = [
                ["Session ID:", session_id],
                ["Round Number:", f"Round {round_number}"],
                ["Generated:", current_time + " UTC"],
                ["Status:", status_text],
                ["Total Clients Analyzed:", str(len(reports))]
            ]
            
            metadata_table = Table(metadata_data, colWidths=[2*inch, 4*inch])
            metadata_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#ebf8ff')),
                ('BACKGROUND', (1, 0), (1, -1), colors.HexColor('#f7fafc')),
                ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#2d3748')),
                ('TEXTCOLOR', (1, 0), (1, 2), colors.HexColor('#2d3748')),
                ('TEXTCOLOR', (1, 3), (1, 3), colors.HexColor(status_color)),
                ('TEXTCOLOR', (1, 4), (1, 4), colors.HexColor('#2d3748')),
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('ALIGN', (1, 0), (1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('LEFTPADDING', (0, 0), (-1, -1), 10),
                ('RIGHTPADDING', (0, 0), (-1, -1), 10),
                ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#cbd5e0')),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0'))
            ]))
            story.append(metadata_table)
            story.append(Spacer(1, 0.3*inch))
            
            # Detailed Client Analysis
            if reports:
                story.append(Paragraph("Detailed Client Analysis", section_style))
                story.append(Spacer(1, 0.1*inch))
                
                summary_text = (f"This report contains detailed analysis for {len(reports)} client(s) "
                               f"identified as potentially malicious during Round {round_number}. "
                               "Each client analysis includes threat score and detection reasoning.")
                story.append(Paragraph(summary_text, explanation_style))
                story.append(Spacer(1, 0.2*inch))
                
                # Process each report
                for idx, report in enumerate(reports):
                    client_id = report.get("client_id", "N/A")
                    explanation = report.get("explanation", "No explanation available.")
                    malicious_score = report.get("malicious_score")
                    
                    # Client header
                    story.append(Paragraph(f"Client {client_id}", client_header_style))
                    
                    story.append(Spacer(1, 0.2*inch))
                    
                    # Client details table - using clean text
                    score_percent = f"{(malicious_score * 100):.1f}%" if malicious_score else "N/A"
                    status = "HIGH RISK" if malicious_score and malicious_score >= 0.5 else "SUSPICIOUS"
                    
                    client_data = [
                        ["Client ID:", str(client_id)],
                        ["Round:", f"Round {round_number}"],
                        # ["Threat Score:", score_percent],
                        # ["Status:", status]
                    ]
                    
                    client_table = Table(client_data, colWidths=[1.5*inch, 4.5*inch])
                    client_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0fff4')),
                        ('BACKGROUND', (1, 0), (1, -1), colors.HexColor('#fffaf0')),
                        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#2d3748')),
                        ('TEXTCOLOR', (1, 0), (1, 1), colors.HexColor('#2d3748')),
                        ('TEXTCOLOR', (1, 2), (1, 2), 
                         colors.HexColor('#c53030' if malicious_score and malicious_score >= 0.5 else '#d69e2e')),
                        ('TEXTCOLOR', (1, 3), (1, 3),
                         colors.HexColor('#c53030' if malicious_score and malicious_score >= 0.5 else '#d69e2e')),
                        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
                        ('FONTSIZE', (0, 0), (-1, -1), 10),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                        ('TOPPADDING', (0, 0), (-1, -1), 6),
                        ('LEFTPADDING', (0, 0), (-1, -1), 8),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#c6f6d5')),
                        ('LINEBELOW', (0, 0), (-1, 0), 0.5, colors.HexColor('#c6f6d5'))
                    ]))
                    story.append(client_table)
                    story.append(Spacer(1, 0.15*inch))
                    
                    # Detection Analysis section
                    story.append(Paragraph("Detection Analysis", 
                                          ParagraphStyle(
                                              'AnalysisHeader',
                                              parent=styles['Heading4'],
                                              fontSize=11,
                                              textColor=colors.HexColor('#4a5568'),
                                              spaceAfter=6,
                                              fontName='Helvetica-Bold'
                                          )))
                    
                    # Clean and format explanation text
                    cleaned_explanation = explanation.strip()
                    
                    # Remove markdown formatting and clean text
                    import re
                    cleaned_explanation = re.sub(r'\*\*(.*?)\*\*', r'\1', cleaned_explanation)  # Remove **bold**
                    cleaned_explanation = re.sub(r'\*(.*?)\*', r'\1', cleaned_explanation)  # Remove *italic*
                    cleaned_explanation = re.sub(r'`(.*?)`', r'\1', cleaned_explanation)  # Remove `code`
                    
                    # Split into paragraphs
                    paragraphs = [p.strip() for p in cleaned_explanation.split('\n') if p.strip()]
                    
                    for para in paragraphs:
                        # Handle numbered lists
                        if re.match(r'^\d+\.\s+', para):
                            # Format as numbered list item
                            story.append(Paragraph(para, ParagraphStyle(
                                'ListNumber',
                                parent=explanation_style,
                                leftIndent=20,
                                firstLineIndent=-15
                            )))
                        # Handle bullet points
                        elif para.startswith(('•', '-', '*', '○')):
                            # Format as bullet point
                            story.append(Paragraph(f"• {para[1:].strip()}", ParagraphStyle(
                                'BulletPoint',
                                parent=explanation_style,
                                leftIndent=20,
                                firstLineIndent=-15
                            )))
                        else:
                            # Regular paragraph
                            story.append(Paragraph(para, explanation_style))
                    
                    story.append(Spacer(1, 0.25*inch))
                    
                    # Add divider between clients (except last one)
                    if idx < len(reports) - 1:
                        story.append(HRFlowable(
                            width="100%",
                            thickness=0.5,
                            color=colors.HexColor('#e2e8f0'),
                            spaceBefore=5,
                            spaceAfter=5
                        ))
                        story.append(Spacer(1, 0.15*inch))
                        
                        # Add page break every 2 clients
                        if (idx + 1) % 2 == 0:
                            story.append(PageBreak())
                            # Add continuation header
                            story.append(Paragraph(
                                f"Session {session_id} - Round {round_number} - Continued",
                                ParagraphStyle(
                                    'Continuation',
                                    parent=subtitle_style,
                                    fontSize=10,
                                    textColor=colors.HexColor('#718096'),
                                    spaceAfter=10
                                )
                            ))
                            story.append(Spacer(1, 0.1*inch))
            else:
                # No threats detected
                story.append(Paragraph("No Threats Detected", section_style))
                story.append(Spacer(1, 0.15*inch))
                
                success_text = ("Security analysis for this round found no malicious activity. "
                               "All clients participated normally in the federated learning process.")
                story.append(Paragraph(success_text, explanation_style))
                story.append(Spacer(1, 0.3*inch))
            
            # Footer
            story.append(Spacer(1, 0.3*inch))
            story.append(HRFlowable(
                width="100%",
                thickness=0.5,
                color=colors.HexColor('#cbd5e0'),
                spaceBefore=10,
                spaceAfter=10
            ))
                        
            story.append(Spacer(1, 0.05*inch))
            story.append(Paragraph(
                f"Report ID: {session_id}_{round_number}_{timestamp}",
                ParagraphStyle(
                    'ReportID',
                    parent=footer_style,
                    fontSize=8,
                    textColor=colors.HexColor('#a0aec0')
                )
            ))
            
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
                fieldnames = [
                    'Client ID', 
                    'Round Number', 
                    'Malicious Score', 
                    'Detection Status', 
                    'Explanation'
                ]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                writer.writeheader()
                
                for report in reports:
                    client_id = report.get("client_id", "N/A")
                    malicious_score = report.get("malicious_score")
                    explanation = report.get("explanation", "")
                    
                    # Clean explanation for CSV
                    explanation_clean = explanation.replace("\n", " ").replace("\r", " ").strip()
                    explanation_clean = ' '.join(explanation_clean.split()[:100])  # Limit to 100 words
                    
                    # Determine status
                    if malicious_score is not None:
                        if malicious_score >= 0.7:
                            status = "HIGH RISK"
                        elif malicious_score >= 0.5:
                            status = "MALICIOUS"
                        elif malicious_score >= 0.3:
                            status = "SUSPICIOUS"
                        else:
                            status = "NORMAL"
                        score_str = f"{malicious_score:.1%}"
                    else:
                        status = "UNKNOWN"
                        score_str = "N/A"
                    
                    writer.writerow({
                        'Client ID': client_id,
                        'Round Number': round_number,
                        'Malicious Score': score_str,
                        'Detection Status': status,
                        'Explanation': explanation_clean
                    })
            
            logger.info(f"✅ CSV report generated successfully: {csv_path}")
            return csv_path
            
        except Exception as e:
            logger.error(f"Error generating CSV report: {e}", exc_info=True)
            return None


def get_pdf_generator() -> PDFReportGenerator:
    """Get PDF report generator"""
    return PDFReportGenerator()
