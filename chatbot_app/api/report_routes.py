"""
Report API Routes

Provides endpoints for accessing generated FL round reports:
- List all reports
- Get reports for a session/round
- Get single report
- Download report as JSON
- Export reports as PDF
"""

import json
import logging
from typing import List, Optional
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db, FLRoundReport
from report_generator import get_report_generator
from pdf_report_generator import PDFReportGenerator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reports", tags=["reports"])


# ============================================================================
# Data Models
# ============================================================================

class ReportItem(BaseModel):
    """Single report item"""
    id: int
    session_id: str
    round_number: int
    client_id: int
    malicious_score: Optional[float] = None
    explanation: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class RoundReportsSummary(BaseModel):
    """Summary of reports for a round"""
    session_id: str
    round_number: int
    report_count: int
    generated_at: datetime
    reports: List[ReportItem]


class SessionReportsSummary(BaseModel):
    """Summary of all reports for a session"""
    session_id: str
    total_rounds_with_reports: int
    total_reports: int
    rounds: List[RoundReportsSummary]


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/", response_model=List[ReportItem])
async def list_reports(
    session_id: Optional[str] = Query(None, description="Filter by session ID"),
    round_number: Optional[int] = Query(None, description="Filter by round number"),
    client_id: Optional[int] = Query(None, description="Filter by client ID"),
    limit: int = Query(100, ge=1, le=1000, description="Limit number of results"),
    skip: int = Query(0, ge=0, description="Skip N results"),
    db: Session = Depends(get_db),
):
    """
    List all reports with optional filters.
    
    Query parameters:
    - session_id: Filter by session ID
    - round_number: Filter by round number
    - client_id: Filter by client ID
    - limit: Maximum number of results (default 100)
    - skip: Skip N results (default 0)
    
    Returns:
        List of reports matching filters
    """
    try:
        query = db.query(FLRoundReport)
        
        # Apply filters
        if session_id:
            query = query.filter(FLRoundReport.session_id == session_id)
        if round_number is not None:
            query = query.filter(FLRoundReport.round_number == round_number)
        if client_id is not None:
            query = query.filter(FLRoundReport.client_id == client_id)
        
        # Order by newest first
        reports = query.order_by(FLRoundReport.created_at.desc()).offset(skip).limit(limit).all()
        
        logger.info(f"Retrieved {len(reports)} reports (session: {session_id}, round: {round_number})")
        return reports
        
    except Exception as e:
        logger.error(f"Error listing reports: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/session/{session_id}", response_model=SessionReportsSummary)
async def get_session_reports(
    session_id: str,
    db: Session = Depends(get_db),
):
    """
    Get all reports for a specific session, organized by round.
    
    Returns:
        Reports grouped by round
    """
    try:
        # Get all reports for this session
        reports = db.query(FLRoundReport).filter(
            FLRoundReport.session_id == session_id
        ).order_by(FLRoundReport.round_number, FLRoundReport.client_id).all()
        
        if not reports:
            raise HTTPException(status_code=404, detail=f"No reports found for session {session_id}")
        
        # Group by round
        rounds_dict = {}
        for report in reports:
            round_num = report.round_number
            if round_num not in rounds_dict:
                rounds_dict[round_num] = {
                    "session_id": session_id,
                    "round_number": round_num,
                    "reports": [],
                    "generated_at": report.created_at
                }
            rounds_dict[round_num]["reports"].append(report)
        
        # Sort rounds by number
        sorted_rounds = []
        for round_num in sorted(rounds_dict.keys()):
            round_data = rounds_dict[round_num]
            sorted_rounds.append(RoundReportsSummary(
                session_id=session_id,
                round_number=round_num,
                report_count=len(round_data["reports"]),
                generated_at=round_data["generated_at"],
                reports=round_data["reports"]
            ))
        
        logger.info(f"Retrieved reports for session {session_id}: {len(sorted_rounds)} rounds")
        
        return SessionReportsSummary(
            session_id=session_id,
            total_rounds_with_reports=len(sorted_rounds),
            total_reports=len(reports),
            rounds=sorted_rounds
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting session reports: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/round/{session_id}/{round_number}", response_model=RoundReportsSummary)
async def get_round_reports(
    session_id: str,
    round_number: int,
    db: Session = Depends(get_db),
):
    """
    Get all reports for a specific round.
    
    Returns:
        Reports for the specified round
    """
    try:
        reports = db.query(FLRoundReport).filter(
            FLRoundReport.session_id == session_id,
            FLRoundReport.round_number == round_number
        ).order_by(FLRoundReport.client_id).all()
        
        if not reports:
            raise HTTPException(
                status_code=404,
                detail=f"No reports found for session {session_id}, round {round_number}"
            )
        
        # Get the timestamp of the first generated report for this round
        generated_at = reports[0].created_at if reports else datetime.utcnow()
        
        logger.info(f"Retrieved {len(reports)} reports for round {round_number}")
        
        return RoundReportsSummary(
            session_id=session_id,
            round_number=round_number,
            report_count=len(reports),
            generated_at=generated_at,
            reports=reports
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting round reports: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/client/{session_id}/{round_number}/{client_id}", response_model=ReportItem)
async def get_client_report(
    session_id: str,
    round_number: int,
    client_id: int,
    db: Session = Depends(get_db),
):
    """
    Get report for a specific client in a round.
    
    Returns:
        Report for the specified client
    """
    try:
        report = db.query(FLRoundReport).filter(
            FLRoundReport.session_id == session_id,
            FLRoundReport.round_number == round_number,
            FLRoundReport.client_id == client_id
        ).first()
        
        if not report:
            raise HTTPException(
                status_code=404,
                detail=f"No report found for session {session_id}, round {round_number}, client {client_id}"
            )
        
        logger.info(f"Retrieved report for client {client_id}")
        return report
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting client report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/download/session/{session_id}")
async def download_session_reports(
    session_id: str,
    db: Session = Depends(get_db),
):
    """
    Download all reports for a session as JSON file.
    
    Returns:
        JSON file with all session reports
    """
    try:
        reports = db.query(FLRoundReport).filter(
            FLRoundReport.session_id == session_id
        ).order_by(FLRoundReport.round_number, FLRoundReport.client_id).all()
        
        if not reports:
            raise HTTPException(status_code=404, detail=f"No reports found for session {session_id}")
        
        # Convert to JSON-serializable format
        reports_data = []
        for report in reports:
            reports_data.append({
                "session_id": report.session_id,
                "round_number": report.round_number,
                "client_id": report.client_id,
                "malicious_score": float(report.malicious_score) if report.malicious_score else None,
                "explanation": report.explanation,
                "created_at": report.created_at.isoformat() if report.created_at else None,
            })
        
        output = {
            "session_id": session_id,
            "download_timestamp": datetime.utcnow().isoformat(),
            "total_reports": len(reports_data),
            "reports": reports_data
        }
        
        # Create JSON response
        json_str = json.dumps(output, indent=2)
        
        logger.info(f"Prepared download for {len(reports_data)} reports")
        
        return StreamingResponse(
            iter([json_str]),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=reports_{session_id}.json"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading session reports: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/download/round/{session_id}/{round_number}")
async def download_round_reports(
    session_id: str,
    round_number: int,
    db: Session = Depends(get_db),
):
    """
    Download all reports for a round as JSON file.
    
    Returns:
        JSON file with round reports
    """
    try:
        reports = db.query(FLRoundReport).filter(
            FLRoundReport.session_id == session_id,
            FLRoundReport.round_number == round_number
        ).order_by(FLRoundReport.client_id).all()
        
        if not reports:
            raise HTTPException(
                status_code=404,
                detail=f"No reports found for session {session_id}, round {round_number}"
            )
        
        # Convert to JSON-serializable format
        reports_data = []
        for report in reports:
            reports_data.append({
                "session_id": report.session_id,
                "round_number": report.round_number,
                "client_id": report.client_id,
                "malicious_score": float(report.malicious_score) if report.malicious_score else None,
                "explanation": report.explanation,
                "created_at": report.created_at.isoformat() if report.created_at else None,
            })
        
        output = {
            "session_id": session_id,
            "round_number": round_number,
            "download_timestamp": datetime.utcnow().isoformat(),
            "total_reports": len(reports_data),
            "reports": reports_data
        }
        
        # Create JSON response
        json_str = json.dumps(output, indent=2)
        
        logger.info(f"Prepared download for {len(reports_data)} round reports")
        
        return StreamingResponse(
            iter([json_str]),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=reports_round_{round_number}.json"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading round reports: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=dict)
async def get_report_stats(
    db: Session = Depends(get_db),
):
    """
    Get statistics about generated reports.
    
    Returns:
        Statistics like total reports, sessions, rounds, etc.
    """
    try:
        total_reports = db.query(FLRoundReport).count()
        total_sessions = db.query(FLRoundReport.session_id).distinct().count()
        total_rounds = db.query(FLRoundReport.round_number).distinct().count()
        total_clients = db.query(FLRoundReport.client_id).distinct().count()
        
        latest_report = db.query(FLRoundReport).order_by(
            FLRoundReport.created_at.desc()
        ).first()
        
        stats = {
            "total_reports": total_reports,
            "total_sessions": total_sessions,
            "total_rounds": total_rounds,
            "total_clients": total_clients,
            "latest_report_timestamp": latest_report.created_at.isoformat() if latest_report else None,
        }
        
        logger.info(f"Report stats: {stats}")
        return stats
        
    except Exception as e:
        logger.error(f"Error getting report stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# PDF Export Endpoints
# ============================================================================

@router.get("/export/round/{session_id}/{round_number}")
async def export_round_reports_to_pdf(
    session_id: str,
    round_number: int,
    db: Session = Depends(get_db),
):
    """
    Export reports for a specific round to PDF format.
    
    Path parameters:
    - session_id: FL session ID
    - round_number: Training round number
    
    Returns:
        PDF file with user-friendly table format
    """
    try:
        logger.info(f"Exporting round reports: session={session_id}, round={round_number}")
        
        # Retrieve reports from database
        reports = db.query(FLRoundReport).filter(
            FLRoundReport.session_id == session_id,
            FLRoundReport.round_number == round_number
        ).all()
        
        if not reports:
            raise HTTPException(
                status_code=404,
                detail=f"No reports found for session {session_id}, round {round_number}"
            )
        
        # Convert to report format
        report_data = [
            {
                "client_id": r.client_id,
                "malicious_score": r.malicious_score,
                "explanation": r.explanation
            }
            for r in reports
        ]
        
        # Generate PDF
        pdf_generator = PDFReportGenerator()
        pdf_path = pdf_generator.generate_pdf_report(
            session_id=session_id,
            round_number=round_number,
            reports=report_data,
            output_path=Path("./reports")
        )
        
        if not pdf_path or not pdf_path.exists():
            raise HTTPException(status_code=500, detail="Failed to generate PDF")
        
        logger.info(f"✅ PDF generated: {pdf_path}")
        
        # Return PDF file
        return FileResponse(
            path=pdf_path,
            filename=pdf_path.name,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={pdf_path.name}"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting reports to PDF: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export/session/{session_id}")
async def export_session_reports_to_pdf(
    session_id: str,
    db: Session = Depends(get_db),
):
    """
    Export ALL reports for an entire session to PDF format.
    
    Path parameters:
    - session_id: FL session ID
    
    Returns:
        PDF file with comprehensive table format for all rounds
    """
    try:
        logger.info(f"Exporting session reports: session={session_id}")
        
        # Retrieve all reports for session
        reports = db.query(FLRoundReport).filter(
            FLRoundReport.session_id == session_id
        ).order_by(FLRoundReport.round_number).all()
        
        if not reports:
            raise HTTPException(
                status_code=404,
                detail=f"No reports found for session {session_id}"
            )
        
        # Convert to report format
        report_data = [
            {
                "client_id": r.client_id,
                "malicious_score": r.malicious_score,
                "explanation": r.explanation
            }
            for r in reports
        ]
        
        # Get max round number for filename
        max_round = max(r.round_number for r in reports) if reports else 0
        
        # Generate PDF
        pdf_generator = PDFReportGenerator()
        pdf_path = pdf_generator.generate_pdf_report(
            session_id=session_id,
            round_number=max_round,
            reports=report_data,
            output_path=Path("./reports")
        )
        
        if not pdf_path or not pdf_path.exists():
            raise HTTPException(status_code=500, detail="Failed to generate PDF")
        
        logger.info(f"✅ PDF generated: {pdf_path}")
        
        # Return PDF file
        return FileResponse(
            path=pdf_path,
            filename=pdf_path.name,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={pdf_path.name}"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting session reports to PDF: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export/round/{session_id}/{round_number}/csv")
async def export_round_reports_to_csv(
    session_id: str,
    round_number: int,
    db: Session = Depends(get_db),
):
    """
    Export reports for a specific round to CSV format.
    
    Path parameters:
    - session_id: FL session ID
    - round_number: Training round number
    
    Returns:
        CSV file with reports
    """
    try:
        logger.info(f"Exporting round reports as CSV: session={session_id}, round={round_number}")
        
        # Retrieve reports from database
        reports = db.query(FLRoundReport).filter(
            FLRoundReport.session_id == session_id,
            FLRoundReport.round_number == round_number
        ).all()
        
        if not reports:
            raise HTTPException(
                status_code=404,
                detail=f"No reports found for session {session_id}, round {round_number}"
            )
        
        # Convert to report format
        report_data = [
            {
                "client_id": r.client_id,
                "malicious_score": r.malicious_score,
                "explanation": r.explanation
            }
            for r in reports
        ]
        
        # Generate CSV
        pdf_generator = PDFReportGenerator()
        csv_path = pdf_generator.generate_csv_report(
            session_id=session_id,
            round_number=round_number,
            reports=report_data,
            output_path=Path("./reports")
        )
        
        if not csv_path or not csv_path.exists():
            raise HTTPException(status_code=500, detail="Failed to generate CSV")
        
        logger.info(f"✅ CSV generated: {csv_path}")
        
        # Return CSV file
        return FileResponse(
            path=csv_path,
            filename=csv_path.name,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={csv_path.name}"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting reports to CSV: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
