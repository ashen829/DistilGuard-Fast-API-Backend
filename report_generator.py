"""
FL Round Report Generator

Generates detailed explanation reports for malicious clients detected in each FL round.
Uses the chatbot LLM with SHAP analysis to create human-readable explanations.

Usage:
    generator = FLReportGenerator()
    reports = await generator.generate_round_reports(
        session_id="2025-01-11_10-30-45",
        round_number=5,
        round_data=round_json,
        db=db_session
    )
"""

import logging
import json
from typing import Optional, Dict, Any, List
from datetime import datetime
from pathlib import Path
from sqlalchemy.orm import Session

from chatbot_app.llm.agent import get_agent
from chatbot_app.llm.shap_csv_analyzer import get_shap_csv_analyzer
from database import FLRoundReport, SessionLocal
from pdf_report_generator import PDFReportGenerator

logger = logging.getLogger(__name__)


class FLReportGenerator:
    """Generates explanation reports for malicious clients in FL rounds"""
    
    def __init__(self):
        """Initialize report generator with LLM agent"""
        try:
            self.agent = get_agent()
            self.shap_analyzer = None
            # Try to get SHAP analyzer (may fail if CSV not available)
            try:
                self.shap_analyzer = get_shap_csv_analyzer()
            except Exception as e:
                logger.warning(f"SHAP analyzer not available: {e}")
            
            logger.info("✓ FL Report Generator initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Report Generator: {e}")
            raise
    
    async def generate_round_reports(
        self,
        session_id: str,
        round_number: int,
        round_data: Dict[str, Any],
        db: Optional[Session] = None,
    ) -> List[Dict[str, Any]]:
        """
        Generate explanation reports for all malicious clients in a round.
        
        Args:
            session_id: Session ID (e.g., "2025-01-11_10-30-45")
            round_number: Training round number
            round_data: Full round JSON data from S3 or constructed from SHAP CSV
            db: Database session (creates new one if None)
        
        Returns:
            List of generated report dictionaries with client_id and explanation
        """
        
        # Create DB session if not provided
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False
        
        try:
            logger.info(f"Generating reports for session {session_id}, round {round_number}")
            
            logger.info(f"ROUND DATA {round_data}")
            
            # Extract malicious clients from round data
            malicious_clients = self._extract_malicious_clients(round_data)
            
            if not malicious_clients:
                logger.info(f"No malicious clients detected in round {round_number}")
                return []
            
            logger.info(f"Found {len(malicious_clients)} malicious clients: {malicious_clients}")
            
            reports = []
            
            # Generate explanation for each malicious client
            for client_info in malicious_clients:
                client_id = client_info.get("client_id")
                malicious_score = client_info.get("score")
                
                logger.info(f"Generating report for client {client_id}")
                
                # Generate explanation using LLM
                explanation = await self._generate_client_explanation(
                    client_id=client_id,
                    session_id=session_id,
                    round_number=round_number,
                    round_data=round_data,
                    malicious_score=malicious_score
                )
                
                if explanation:
                    # Store report in database
                    report = FLRoundReport(
                        session_id=session_id,
                        round_number=round_number,
                        client_id=client_id,
                        malicious_score=malicious_score,
                        explanation=explanation,
                        report_data={
                            "client_info": client_info,
                            "generated_at": datetime.utcnow().isoformat()
                        },
                        timestamp=datetime.utcnow()
                    )
                    db.add(report)
                    
                    reports.append({
                        "client_id": client_id,
                        "malicious_score": malicious_score,
                        "explanation": explanation
                    })
                    
                    logger.info(f"✓ Report generated for client {client_id}")
                else:
                    logger.warning(f"⚠️  Failed to generate report for client {client_id}")
            
            # Commit all reports
            if reports:
                db.commit()
                logger.info(f"✅ Committed {len(reports)} reports to database")
            
            return reports
            
        except Exception as e:
            logger.error(f"Error generating round reports: {e}", exc_info=True)
            db.rollback()
            return []
        finally:
            if close_db:
                db.close()
    
    async def generate_reports_from_shap_csv_row(
        self,
        session_id: str,
        round_number: int,
        client_id: int,
        csv_row: Dict[str, Any],
        db: Optional[Session] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Generate a report for a single malicious client from SHAP CSV row data.
        
        This method is specifically designed to handle individual rows from SHAP CSV,
        where we have all the metrics directly available without needing full round JSON.
        
        Args:
            session_id: Session ID
            round_number: Training round number
            client_id: Client ID
            csv_row: Dictionary with SHAP CSV row data
            db: Database session (creates new one if None)
        
        Returns:
            Generated report dictionary or None if generation fails
        """
        # Create DB session if not provided
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False
        
        try:
            logger.info(f"Generating report for client {client_id} from SHAP CSV data")
            
            # Extract malicious score if available
            malicious_score = csv_row.get('confidence', 0.95)
            
            # Create minimal round data for the report generator
            round_data = {
                'metadata': {'round': round_number},
                'clients': [
                    {
                        'client_id': client_id,
                        'clientId': client_id,
                        'isMalicious': True,
                        'is_malicious': True,
                        'predicted_label': csv_row.get('predicted_label', 'malicious'),
                        'ground_truth_label': csv_row.get('ground_truth_label', 'unknown'),
                        'main_task_accuracy': float(csv_row.get('main_task_accuracy', 0)) if csv_row.get('main_task_accuracy') else 0,
                        'main_task_loss': float(csv_row.get('main_task_loss', 0)) if csv_row.get('main_task_loss') else 0,
                    }
                ],
                'globalMetrics': {
                    'detectedClients': [{'clientId': client_id, 'score': malicious_score}]
                }
            }
            
            # Generate explanation
            explanation = await self._generate_client_explanation(
                client_id=client_id,
                session_id=session_id,
                round_number=round_number,
                round_data=round_data,
                malicious_score=malicious_score
            )
            
            if explanation:
                # Store in database
                report = FLRoundReport(
                    session_id=session_id,
                    round_number=round_number,
                    client_id=client_id,
                    malicious_score=malicious_score,
                    explanation=explanation,
                    report_data={
                        "source": "shap_csv",
                        "csv_row": csv_row,
                        "generated_at": datetime.utcnow().isoformat()
                    },
                    timestamp=datetime.utcnow()
                )
                db.add(report)
                db.commit()
                
                logger.info(f"✓ Report generated and stored for client {client_id}")
                
                return {
                    "client_id": client_id,
                    "round_number": round_number,
                    "malicious_score": malicious_score,
                    "explanation": explanation
                }
            else:
                logger.warning(f"⚠️  Failed to generate explanation for client {client_id}")
                return None
            
        except Exception as e:
            logger.error(f"Error generating report from SHAP CSV: {e}", exc_info=True)
            db.rollback()
            return None
        finally:
            if close_db:
                db.close()
    
    async def _generate_client_explanation(
        self,
        client_id: int,
        session_id: str,
        round_number: int,
        round_data: Dict[str, Any],
        malicious_score: Optional[float] = None
    ) -> Optional[str]:
        """
        Generate LLM explanation for why a client is detected as malicious.
        
        Uses SHAP analysis if available, otherwise uses generic analysis.
        
        Args:
            client_id: Client ID
            session_id: Session ID
            round_number: Round number
            round_data: Full round data
            malicious_score: Detection/malicious score (e.g., confidence)
        
        Returns:
            Natural language explanation or None if generation fails
        """
        try:
            # Build context
            context = self._build_client_context(
                client_id=client_id,
                round_number=round_number,
                round_data=round_data,
                malicious_score=malicious_score
            )
            
            # Build prompt for LLM
            prompt = self._build_explanation_prompt(
                client_id=client_id,
                context=context,
                malicious_score=malicious_score
            )
            
            logger.info(f"Generating explanation via agent for client {client_id}")
            
            # Use agent to generate explanation
            # The agent's process method handles LLM call with proper context
            explanation = self.agent.process(
                user_input=prompt,
                chat_history=[]
            )
            
            return explanation
            
        except Exception as e:
            logger.error(f"Error generating explanation for client {client_id}: {e}", exc_info=True)
            return None
    
    def _build_client_context(
        self,
        client_id: int,
        round_number: int,
        round_data: Dict[str, Any],
        malicious_score: Optional[float] = None
    ) -> Dict[str, Any]:
        """Build context information about a client"""
        
        context = {
            "client_id": client_id,
            "round_number": round_number,
            "malicious_score": malicious_score
        }
        
        # Extract client data from round
        clients = round_data.get("clients", [])
        for client in clients:
            if client.get("clientId") == client_id or client.get("client_id") == client_id:
                context["client_data"] = client
                break
        
        # Try to get SHAP analysis if available
        if self.shap_analyzer:
            try:
                shap_data = self.shap_analyzer.get_top_shap_features_for_client(
                    client_id=client_id,
                    top_n=5
                )
                if shap_data:
                    context["shap_analysis"] = shap_data
                    logger.info(f"✓ Got SHAP analysis for client {client_id}")
            except Exception as e:
                logger.debug(f"Could not get SHAP analysis for client {client_id}: {e}")
        
        return context
    
    def _build_explanation_prompt(
        self,
        client_id: int,
        context: Dict[str, Any],
        malicious_score: Optional[float] = None
    ) -> str:
        """Build the prompt to ask the LLM with SHAP feature context (non-technical explanation)"""
        
        # Build SHAP context for better explanations (without malicious score)
        shap_context = ""
        if "shap_analysis" in context and context["shap_analysis"]:
            shap_context = context["shap_analysis"]
        
        # If we have SHAP features, use them for the prompt
        if shap_context:
            prompt = f"""**Client {client_id} Behavior Analysis**

Top Contributing Features:
{shap_context}

**Your Task:**
Write a clear, simple explanation for someone without technical background. 
- Focus on what the top features reveal about this client's behavior
- Use simple language, not machine learning jargon
- Explain what each abnormal feature value means in practical terms
- Help readers understand why these patterns indicate suspicious activity
- Keep it concise but informative"""
        else:
            # Fallback if no SHAP context available
            prompt = f"""Why is client {client_id} detected as malicious?

Provide a clear explanation suitable for non-technical readers:
- Describe what indicators led to this detection
- Explain the significance of any unusual metrics
- Use simple, everyday language
- Avoid technical jargon"""
        
        return prompt
    
    def _extract_malicious_clients(self, round_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract list of malicious clients from round data.
        
        Args:
            round_data: Round JSON data from S3
        
        Returns:
            List of dicts with client_id and optional score
        """
        malicious_clients = []
        
        try:
            # Try to get from globalMetrics
            global_metrics = round_data.get("globalMetrics", {})
            detected_clients = global_metrics.get("detectedClients", [])
            
            if detected_clients:
                # detectedClients is a list of client IDs or objects
                for item in detected_clients:
                    if isinstance(item, dict):
                        client_id = item.get("clientId") or item.get("client_id")
                        score = item.get("score") or item.get("maliciousScore")
                        if client_id is not None:
                            malicious_clients.append({
                                "client_id": int(client_id),
                                "score": float(score) if score else None
                            })
                    elif isinstance(item, int):
                        malicious_clients.append({
                            "client_id": int(item),
                            "score": None
                        })
            
            # Alternative: check roundSummary
            if not malicious_clients:
                round_summary = round_data.get("roundSummary", {})
                suspicious_clients = round_summary.get("suspiciousClients", [])
                if suspicious_clients:
                    for client_id in suspicious_clients:
                        malicious_clients.append({
                            "client_id": int(client_id),
                            "score": None
                        })
            
            # Alternative: check clients array for labeled malicious clients
            if not malicious_clients:
                clients = round_data.get("clients", [])
                for client in clients:
                    if client.get("isMalicious") or client.get("is_malicious") or client.get("malicious"):
                        client_id = client.get("clientId") or client.get("client_id")
                        score = client.get("maliciousScore") or client.get("score")
                        if client_id is not None:
                            malicious_clients.append({
                                "client_id": int(client_id),
                                "score": float(score) if score else None
                            })
            
            logger.info(f"Extracted {len(malicious_clients)} malicious clients")
            return malicious_clients
            
        except Exception as e:
            logger.error(f"Error extracting malicious clients: {e}")
            return []
    
    async def export_round_reports_to_pdf(
        self,
        session_id: str,
        round_number: int,
        db: Optional[Session] = None,
        output_path: Optional[Path] = None
    ) -> Optional[Path]:
        """
        Export reports for a specific round to a user-friendly PDF file.
        
        Args:
            session_id: Session ID
            round_number: Round number
            db: Database session (creates new one if None)
            output_path: Output directory for PDF (default: ./reports/)
        
        Returns:
            Path to generated PDF file or None if generation fails
        """
        
        # Create DB session if not provided
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False
        
        try:
            logger.info(f"Exporting reports for session {session_id}, round {round_number} to PDF")
            
            # Retrieve all reports for this session and round from database
            reports = db.query(FLRoundReport).filter(
                FLRoundReport.session_id == session_id,
                FLRoundReport.round_number == round_number
            ).all()
            
            if not reports:
                logger.warning(f"No reports found for session {session_id}, round {round_number}")
                return None
            
            logger.info(f"Found {len(reports)} reports to export")
            
            # Convert reports to format expected by PDF generator
            report_data = []
            for report in reports:
                report_data.append({
                    "client_id": report.client_id,
                    "malicious_score": report.malicious_score,
                    "explanation": report.explanation
                })
            
            # Generate PDF
            pdf_generator = PDFReportGenerator()
            pdf_path = pdf_generator.generate_pdf_report(
                session_id=session_id,
                round_number=round_number,
                reports=report_data,
                output_path=output_path
            )
            
            if pdf_path:
                logger.info(f"✅ PDF report exported: {pdf_path}")
            
            return pdf_path
            
        except Exception as e:
            logger.error(f"Error exporting reports to PDF: {e}", exc_info=True)
            return None
        finally:
            if close_db:
                db.close()
    
    async def export_session_reports_to_pdf(
        self,
        session_id: str,
        db: Optional[Session] = None,
        output_path: Optional[Path] = None
    ) -> Optional[Path]:
        """
        Export ALL reports for an entire session to PDF.
        
        Args:
            session_id: Session ID
            db: Database session (creates new one if None)
            output_path: Output directory for PDF (default: ./reports/)
        
        Returns:
            Path to generated PDF file or None if generation fails
        """
        
        # Create DB session if not provided
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False
        
        try:
            logger.info(f"Exporting all reports for session {session_id} to PDF")
            
            # Retrieve all reports for this session from database
            reports = db.query(FLRoundReport).filter(
                FLRoundReport.session_id == session_id
            ).order_by(FLRoundReport.round_number).all()
            
            if not reports:
                logger.warning(f"No reports found for session {session_id}")
                return None
            
            logger.info(f"Found {len(reports)} reports to export")
            
            # Convert reports to format expected by PDF generator
            report_data = []
            round_numbers = set()
            for report in reports:
                report_data.append({
                    "client_id": report.client_id,
                    "malicious_score": report.malicious_score,
                    "explanation": report.explanation
                })
                round_numbers.add(report.round_number)
            
            # Generate PDF (using max round number for filename)
            max_round = max(round_numbers) if round_numbers else 0
            pdf_generator = PDFReportGenerator()
            pdf_path = pdf_generator.generate_pdf_report(
                session_id=session_id,
                round_number=max_round,  # Use max round in filename
                reports=report_data,
                output_path=output_path
            )
            
            if pdf_path:
                logger.info(f"✅ Full session PDF report exported: {pdf_path}")
            
            return pdf_path
            
        except Exception as e:
            logger.error(f"Error exporting session reports to PDF: {e}", exc_info=True)
            return None
        finally:
            if close_db:
                db.close()


# Global instance
_generator: Optional[FLReportGenerator] = None


def get_report_generator() -> FLReportGenerator:
    """Get or initialize the report generator"""
    global _generator
    if _generator is None:
        _generator = FLReportGenerator()
    return _generator


def reset_generator():
    """Reset the global generator instance"""
    global _generator
    _generator = None
