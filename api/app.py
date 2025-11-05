"""
Hydropage Flask API

REST API for accessing hydropower plant data, analytics, and matching results.

Endpoints:
    GET  /api/plants               - List all verified matched plants
    GET  /api/plants/<id>          - Get specific plant details
    GET  /api/plants/search        - Search plants by criteria
    GET  /api/stats                - Get system statistics
    GET  /api/stats/states         - Get state-level statistics
    GET  /api/matches/pending      - Get matches pending review
    GET  /api/analysis/inoperable  - Get inoperable but licensed plants
    GET  /api/analysis/reactivation- Get reactivation candidates
    GET  /api/health               - API health check
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import sqlite3
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from dotenv import load_dotenv
import sys

# Load environment variables
load_dotenv()

# Fix Unicode encoding for Windows console
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

# Initialize Flask app
app = Flask(__name__)

# CORS Configuration - Allow all origins for development
# This enables full CORS support including preflight requests
CORS(app)

# Configuration
# Use local database in production (Railway), or parent directory in development
app.config['DATABASE'] = os.path.join(os.path.dirname(__file__), 'hydropage.db')
app.config['JSON_SORT_KEYS'] = False


# =============================================================================
# Database Helper Functions
# =============================================================================

def get_db():
    """Get database connection."""
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.row_factory = sqlite3.Row  # Return rows as dictionaries
    return conn


def query_db(query: str, args: Tuple = (), one: bool = False):
    """
    Execute a database query and return results.

    Args:
        query: SQL query string
        args: Query arguments
        one: If True, return only first result

    Returns:
        Query results as list of dictionaries (or single dict if one=True)
    """
    conn = get_db()
    cur = conn.cursor()
    cur.execute(query, args)
    rv = cur.fetchall()
    conn.close()

    # Convert Row objects to dictionaries
    results = [dict(row) for row in rv]
    return results[0] if (results and one) else results


# =============================================================================
# API Response Helpers
# =============================================================================

class APIResponse:
    """Standardized API response formatter."""

    @staticmethod
    def success(data: Any, pagination: Optional[Dict] = None, meta: Optional[Dict] = None):
        """
        Return successful response with optional pagination.

        Args:
            data: Response data (dict, list, etc.)
            pagination: Optional pagination metadata
            meta: Optional additional metadata

        Returns:
            Flask JSON response with 200 status
        """
        response = {
            'status': 'success',
            'data': data
        }

        if pagination:
            response['pagination'] = pagination

        if meta:
            response['meta'] = meta

        return jsonify(response), 200

    @staticmethod
    def error(message: str, code: str = 'ERROR', status: int = 400, details: Optional[Dict] = None):
        """
        Return error response with standardized format.

        Args:
            message: Human-readable error message
            code: Machine-readable error code
            status: HTTP status code
            details: Optional additional error details

        Returns:
            Flask JSON response with error status
        """
        response = {
            'status': 'error',
            'error': {
                'code': code,
                'message': message,
                'status': status
            }
        }

        if details:
            response['error']['details'] = details

        return jsonify(response), status

    @staticmethod
    def paginate(total: int, page: int, per_page: int) -> Dict:
        """
        Generate pagination metadata.

        Args:
            total: Total number of records
            page: Current page (1-indexed)
            per_page: Records per page

        Returns:
            Pagination metadata dictionary
        """
        total_pages = (total + per_page - 1) // per_page if per_page > 0 else 0

        return {
            'page': page,
            'per_page': per_page,
            'total': total,
            'total_pages': total_pages,
            'has_next': page < total_pages,
            'has_prev': page > 1
        }


# =============================================================================
# API Endpoints
# =============================================================================

@app.route('/', methods=['GET'])
def root():
    """Root endpoint with API documentation."""
    return jsonify({
        'name': 'Hydropage API',
        'version': '1.0.0',
        'description': 'REST API for US hydropower plant data (FERC + EIA)',
        'documentation': {
            'health': '/api/health - API health check',
            'statistics': {
                'overall': '/api/stats - System statistics',
                'by_state': '/api/stats/states - State-level breakdown'
            },
            'plants': {
                'list': '/api/plants?state=WA&min_capacity=100 - List plants (filterable)',
                'details': '/api/plants/<id> - Get plant details (P-#### or plant_id)',
                'search': '/api/plants/search?q=coulee - Search by name'
            },
            'matching': {
                'pending': '/api/matches/pending - Matches awaiting review'
            },
            'analysis': {
                'inoperable': '/api/analysis/inoperable - Licensed but not operating',
                'reactivation': '/api/analysis/reactivation - Reactivation candidates',
                'relicensing': '/api/analysis/relicensing?urgency=critical - Relicensing urgency'
            }
        },
        'data_sources': {
            'FERC': 'Federal Energy Regulatory Commission (licensing data)',
            'EIA': 'Energy Information Administration (operational data)'
        }
    })


@app.route('/api/health', methods=['GET'])
def health_check():
    """API health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '1.0.0'
    })


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get overall system statistics."""
    stats = {}

    # FERC statistics
    ferc_query = """
        SELECT
            COUNT(*) as total_ferc,
            COUNT(CASE WHEN expiration_status = 'Critical' THEN 1 END) as critical_expirations,
            COUNT(CASE WHEN has_pending_application = 1 THEN 1 END) as pending_applications,
            SUM(capacity_mw) as total_ferc_capacity
        FROM licensing_status
    """
    ferc_stats = query_db(ferc_query, one=True)
    stats['ferc'] = ferc_stats

    # EIA statistics
    eia_query = """
        SELECT
            COUNT(*) as total_eia,
            COUNT(CASE WHEN operational_status = 'OP' THEN 1 END) as operating,
            COUNT(CASE WHEN operational_status = 'RE' THEN 1 END) as retired,
            COUNT(CASE WHEN operational_status IN ('OS', 'SB') THEN 1 END) as out_of_service,
            SUM(nameplate_capacity_mw) as total_eia_capacity
        FROM operational_status
    """
    eia_stats = query_db(eia_query, one=True)
    stats['eia'] = eia_stats

    # Matching statistics
    match_query = """
        SELECT
            COUNT(*) as total_matches,
            COUNT(CASE WHEN match_status = 'auto' THEN 1 END) as auto_approved,
            COUNT(CASE WHEN match_status = 'verified' THEN 1 END) as verified,
            COUNT(CASE WHEN match_status = 'pending' THEN 1 END) as pending_review,
            AVG(match_score) as avg_match_score
        FROM ferc_eia_matches
    """
    match_stats = query_db(match_query, one=True)
    stats['matching'] = match_stats

    # Production statistics (if available)
    prod_query = """
        SELECT
            COUNT(DISTINCT plant_id) as plants_with_production,
            SUM(generation_mwh) as total_generation_mwh,
            COUNT(*) as total_production_records
        FROM energy_production
    """
    prod_stats = query_db(prod_query, one=True)
    stats['production'] = prod_stats

    return jsonify(stats)


@app.route('/api/stats/states', methods=['GET'])
def get_state_stats():
    """Get state-level statistics."""
    query = """
        SELECT
            state,
            COUNT(DISTINCT ferc_project_number) as ferc_plants,
            COUNT(DISTINCT eia_plant_id) as eia_plants,
            COALESCE(SUM(capacity_mw), 0) as total_capacity_mw,
            COUNT(CASE WHEN is_inoperable_but_licensed = 1 THEN 1 END) as inoperable_licensed,
            COUNT(CASE WHEN is_reactivation_candidate = 1 THEN 1 END) as reactivation_candidates
        FROM hydropower_projects
        GROUP BY state
        ORDER BY total_capacity_mw DESC
    """
    results = query_db(query)
    return jsonify(results)


@app.route('/api/plants', methods=['GET'])
def get_plants():
    """
    Get list of hydropower plants with optional filtering.

    Query Parameters:
        state: Filter by state code (e.g., WA)
        status: Filter by operational status (OP, RE, OS, SB, TS)
        ownership_type: Filter by ownership (Private, Municipal, Federal, Cooperative)
        min_capacity: Minimum capacity in MW
        max_capacity: Maximum capacity in MW
        limit: Maximum number of results (default: 25, max: 1000)
        offset: Pagination offset (default: 0)
    """
    # Get query parameters
    state = request.args.get('state')
    status = request.args.get('status')
    ownership_type = request.args.get('ownership_type')
    min_capacity = request.args.get('min_capacity', type=float)
    max_capacity = request.args.get('max_capacity', type=float)
    limit = request.args.get('limit', default=25, type=int)
    offset = request.args.get('offset', default=0, type=int)

    # Input validation
    valid_statuses = ['OP', 'RE', 'OS', 'SB', 'TS']
    if status and status.upper() not in valid_statuses:
        return APIResponse.error(
            message=f'Invalid status. Must be one of: {", ".join(valid_statuses)}',
            code='INVALID_STATUS',
            status=400
        )

    if limit < 1 or limit > 1000:
        return APIResponse.error(
            message='Limit must be between 1 and 1000',
            code='INVALID_LIMIT',
            status=400
        )

    if offset < 0:
        return APIResponse.error(
            message='Offset must be non-negative',
            code='INVALID_OFFSET',
            status=400
        )

    if min_capacity is not None and min_capacity < 0:
        return APIResponse.error(
            message='Minimum capacity must be non-negative',
            code='INVALID_CAPACITY',
            status=400
        )

    if max_capacity is not None and min_capacity is not None and max_capacity < min_capacity:
        return APIResponse.error(
            message='Maximum capacity must be greater than minimum capacity',
            code='INVALID_CAPACITY_RANGE',
            status=400
        )

    # Build query
    query = """
        SELECT
            match_id,
            ferc_project_number,
            ferc_project_name,
            eia_plant_id,
            eia_plant_name,
            state,
            county,
            capacity_mw,
            operational_status,
            expiration_date,
            years_until_expiration,
            latitude,
            longitude,
            licensee,
            operator_name,
            is_inoperable_but_licensed,
            is_reactivation_candidate,
            match_score
        FROM hydropower_projects
        WHERE 1=1
    """
    params = []

    if state:
        query += " AND state = ?"
        params.append(state)

    if status:
        query += " AND operational_status = ?"
        params.append(status)

    if ownership_type:
        query += " AND ownership_type = ?"
        params.append(ownership_type)

    if min_capacity is not None:
        query += " AND capacity_mw >= ?"
        params.append(min_capacity)

    if max_capacity is not None:
        query += " AND capacity_mw <= ?"
        params.append(max_capacity)

    query += " ORDER BY capacity_mw DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    results = query_db(query, tuple(params))

    # Get total count for pagination
    count_query = "SELECT COUNT(*) as total FROM hydropower_projects WHERE 1=1"
    count_params = []

    if state:
        count_query += " AND state = ?"
        count_params.append(state)
    if status:
        count_query += " AND operational_status = ?"
        count_params.append(status)
    if ownership_type:
        count_query += " AND ownership_type = ?"
        count_params.append(ownership_type)
    if min_capacity is not None:
        count_query += " AND capacity_mw >= ?"
        count_params.append(min_capacity)
    if max_capacity is not None:
        count_query += " AND capacity_mw <= ?"
        count_params.append(max_capacity)

    total = query_db(count_query, tuple(count_params), one=True)['total']

    # Calculate current page (1-indexed)
    page = (offset // limit) + 1 if limit > 0 else 1

    # Use standardized response format
    pagination = APIResponse.paginate(total, page, limit)

    return APIResponse.success(
        data=results,
        pagination=pagination,
        meta={'filters_applied': sum([1 for p in [state, status, ownership_type, min_capacity, max_capacity] if p is not None])}
    )


@app.route('/api/plants/<id>', methods=['GET'])
def get_plant_details(id):
    """
    Get detailed aggregated information about a specific plant.

    Can use either FERC project number (P-####) or EIA plant ID.

    Returns comprehensive data including:
    - Basic plant information
    - FERC licensing details
    - EIA operational data
    - Production history and statistics
    - Match information and data quality
    """
    # Try to parse as integer (EIA plant ID) or string (FERC project number)
    # First check hydropower_projects view (matched FERC+EIA records)
    query = """
        SELECT *
        FROM hydropower_projects
        WHERE eia_plant_id = ? OR ferc_project_number = ?
    """

    # Try to convert to int for EIA plant ID
    try:
        eia_id = int(id.replace('P-', '').replace('p-', ''))
        plant = query_db(query, (eia_id, id), one=True)
    except ValueError:
        plant = query_db(query, (None, id), one=True)

    # If not found in matched records, check FERC-only records
    if not plant and id.upper().startswith('P-'):
        ferc_query = """
            SELECT
                project_number as ferc_project_number,
                project_name as ferc_project_name,
                licensee,
                state,
                county,
                river_stream,
                capacity_mw,
                expiration_date,
                days_until_expiration,
                years_until_expiration,
                expiration_status,
                has_pending_application,
                license_type,
                ownership_type,
                ferc_lat,
                ferc_lon,
                data_source_url,
                last_updated
            FROM licensing_status
            WHERE project_number = ?
        """
        plant = query_db(ferc_query, (id,), one=True)

        if plant:
            # Mark as FERC-only record
            plant['is_ferc_only'] = True

    if not plant:
        return jsonify({'error': 'Plant not found'}), 404

    # Build comprehensive plant profile
    plant_profile = {
        'basic_info': {
            'ferc_project_number': plant.get('ferc_project_number'),
            'ferc_project_name': plant.get('ferc_project_name'),
            'eia_plant_id': plant.get('eia_plant_id'),
            'eia_plant_name': plant.get('eia_plant_name'),
            'state': plant.get('state'),
            'county': plant.get('county'),
            'river_stream': plant.get('river_stream'),
            'location': {
                'latitude': plant.get('latitude'),
                'longitude': plant.get('longitude')
            }
        },
        'licensing': {
            'licensee': plant.get('licensee'),
            'expiration_date': plant.get('expiration_date'),
            'days_until_expiration': plant.get('days_until_expiration'),
            'years_until_expiration': plant.get('years_until_expiration'),
            'expiration_status': plant.get('expiration_status'),
            'has_pending_application': plant.get('has_pending_application'),
            'license_type': plant.get('license_type')
        },
        'operational': {
            'operator_name': plant.get('operator_name'),
            'operational_status': plant.get('operational_status'),
            'in_service_date': plant.get('in_service_date'),
            'retirement_date': plant.get('retirement_date')
        },
        'capacity': {
            'capacity_mw': plant.get('capacity_mw'),
            'nameplate_capacity_mw': plant.get('nameplate_capacity_mw')
        },
        'analysis': {
            'is_inoperable_but_licensed': plant.get('is_inoperable_but_licensed'),
            'is_reactivation_candidate': plant.get('is_reactivation_candidate')
        },
        'match_info': {
            'match_id': plant.get('match_id'),
            'match_status': plant.get('match_status'),
            'match_score': plant.get('match_score')
        }
    }

    # Get production data if available
    if plant.get('eia_plant_id'):
        # Recent 12 months
        prod_query = """
            SELECT year, month, generation_mwh, capacity_factor
            FROM energy_production
            WHERE plant_id = ?
            ORDER BY year DESC, month DESC
            LIMIT 12
        """
        recent_production = query_db(prod_query, (plant['eia_plant_id'],))

        # Annual production statistics
        annual_stats_query = """
            SELECT
                year,
                COUNT(*) as months_reported,
                SUM(generation_mwh) as total_generation_mwh,
                AVG(generation_mwh) as avg_monthly_generation_mwh,
                AVG(capacity_factor) as avg_capacity_factor
            FROM energy_production
            WHERE plant_id = ?
            GROUP BY year
            ORDER BY year DESC
            LIMIT 5
        """
        annual_stats = query_db(annual_stats_query, (plant['eia_plant_id'],))

        # Lifetime statistics
        lifetime_stats_query = """
            SELECT
                MIN(year) as first_year_reported,
                MAX(year) as latest_year_reported,
                COUNT(DISTINCT year) as years_of_data,
                COUNT(*) as total_months_reported,
                SUM(generation_mwh) as lifetime_generation_mwh,
                AVG(generation_mwh) as avg_monthly_generation_mwh,
                MAX(generation_mwh) as peak_monthly_generation_mwh,
                AVG(capacity_factor) as avg_capacity_factor
            FROM energy_production
            WHERE plant_id = ?
        """
        lifetime_stats = query_db(lifetime_stats_query, (plant['eia_plant_id'],), one=True)

        plant_profile['production'] = {
            'recent_12_months': recent_production,
            'annual_statistics': annual_stats,
            'lifetime_statistics': lifetime_stats
        }
    else:
        plant_profile['production'] = {
            'message': 'No production data available for this plant'
        }

    # Add FERC licensing details if available
    if plant.get('ferc_project_number'):
        ferc_query = """
            SELECT
                project_number,
                project_name,
                licensee,
                state,
                county,
                river_stream,
                capacity_mw,
                expiration_date,
                license_type,
                ownership_type,
                ferc_lat,
                ferc_lon,
                data_source_url,
                last_updated
            FROM licensing_status
            WHERE project_number = ?
        """
        ferc_details = query_db(ferc_query, (plant['ferc_project_number'],), one=True)

        if ferc_details:
            plant_profile['ferc_details'] = ferc_details

    # Add EIA operational details if available
    if plant.get('eia_plant_id'):
        eia_query = """
            SELECT
                plant_id,
                plant_name,
                operator_name,
                state,
                county,
                latitude,
                longitude,
                nameplate_capacity_mw,
                operational_status,
                in_service_date,
                retirement_date,
                energy_source,
                technology_description,
                ownership_type,
                balancing_authority,
                last_updated
            FROM operational_status
            WHERE plant_id = ?
        """
        eia_details = query_db(eia_query, (plant['eia_plant_id'],), one=True)

        if eia_details:
            plant_profile['eia_details'] = eia_details

    return jsonify(plant_profile)


@app.route('/api/plants/search', methods=['GET'])
def search_plants():
    """
    Search plants by name or location.

    Query Parameters:
        q: Search query (searches plant names)
        state: Filter by state
        limit: Maximum results (default: 20)
    """
    query_text = request.args.get('q', '').strip()
    state = request.args.get('state')
    limit = request.args.get('limit', default=20, type=int)

    if not query_text:
        return jsonify({'error': 'Search query (q) required'}), 400

    query = """
        SELECT
            ferc_project_number,
            ferc_project_name,
            eia_plant_id,
            eia_plant_name,
            state,
            capacity_mw,
            operational_status
        FROM hydropower_projects
        WHERE (ferc_project_name LIKE ? OR eia_plant_name LIKE ?)
    """
    params = [f"%{query_text}%", f"%{query_text}%"]

    if state:
        query += " AND state = ?"
        params.append(state)

    query += " ORDER BY capacity_mw DESC LIMIT ?"
    params.append(limit)

    results = query_db(query, tuple(params))
    return jsonify(results)


@app.route('/api/matches/pending', methods=['GET'])
def get_pending_matches():
    """Get matches pending human review."""
    confidence = request.args.get('confidence', '')  # filter by confidence level

    query = """
        SELECT
            m.match_id,
            m.match_score,
            m.match_confidence,
            m.match_status,
            m.name_similarity,
            m.distance_km,
            m.capacity_diff_percent,
            m.state_match,
            m.county_match,
            m.river_match_score,
            l.project_number as ferc_project_number,
            l.project_name as ferc_project_name,
            l.licensee,
            l.state as ferc_state,
            l.county as ferc_county,
            l.river_stream,
            l.capacity_mw as ferc_capacity_mw,
            l.expiration_date,
            l.ownership_type as ferc_ownership,
            o.plant_id as eia_plant_id,
            o.plant_name as eia_plant_name,
            o.operator_name,
            o.state as eia_state,
            o.county as eia_county,
            o.latitude,
            o.longitude,
            o.nameplate_capacity_mw as eia_capacity_mw,
            o.operational_status,
            o.ownership_type as eia_ownership
        FROM ferc_eia_matches m
        LEFT JOIN licensing_status l ON m.ferc_project_number = l.project_number
        LEFT JOIN operational_status o ON m.eia_plant_id = o.plant_id
        WHERE m.match_status = 'pending'
    """

    # Validate confidence parameter to prevent SQL injection
    valid_confidences = ['high', 'medium', 'low']
    params = []

    if confidence:
        if confidence.lower() not in valid_confidences:
            return jsonify({'error': f'Invalid confidence value. Must be one of: {", ".join(valid_confidences)}'}), 400
        query += " AND m.match_confidence = ?"
        params.append(confidence.lower())

    query += " ORDER BY m.match_score DESC"

    results = query_db(query, tuple(params))
    return jsonify({'matches': results})


@app.route('/api/analysis/inoperable', methods=['GET'])
def get_inoperable_plants():
    """Get plants that are licensed but not operating."""
    query = """
        SELECT *
        FROM hydropower_projects
        WHERE is_inoperable_but_licensed = 1
        ORDER BY capacity_mw DESC
    """
    results = query_db(query)
    return jsonify(results)


@app.route('/api/analysis/reactivation', methods=['GET'])
def get_reactivation_candidates():
    """Get plants that are candidates for reactivation."""
    query = """
        SELECT *
        FROM hydropower_projects
        WHERE is_reactivation_candidate = 1
        ORDER BY capacity_mw DESC
    """
    results = query_db(query)
    return jsonify(results)


@app.route('/api/analysis/relicensing', methods=['GET'])
def get_relicensing_urgency():
    """Get plants approaching license expiration."""
    urgency = request.args.get('urgency', 'all')  # critical, near-term, mid-term, all

    query = """
        SELECT
            ferc_project_number,
            ferc_project_name,
            state,
            capacity_mw,
            expiration_date,
            days_until_expiration,
            years_until_expiration,
            expiration_status,
            has_pending_application,
            operational_status
        FROM hydropower_projects
        WHERE expiration_date IS NOT NULL
    """

    if urgency != 'all':
        query += " AND expiration_status = ?"
        params = [urgency.capitalize()]
    else:
        params = []

    query += " ORDER BY days_until_expiration ASC"

    results = query_db(query, tuple(params))
    return jsonify(results)


@app.route('/api/analysis/small-llc-owners', methods=['GET'])
def get_small_llc_owners():
    """
    Get small private/LLC owners (1-2 projects only).
    Filters out large corporations with many projects.
    """
    query = """
        WITH owner_counts AS (
            SELECT
                licensee,
                COUNT(*) as project_count
            FROM licensing_status
            WHERE ownership_type = 'Private'
            AND licensee IS NOT NULL
            GROUP BY licensee
        )
        SELECT
            l.*,
            oc.project_count
        FROM licensing_status l
        JOIN owner_counts oc ON l.licensee = oc.licensee
        WHERE oc.project_count <= 2
        AND (
            l.licensee LIKE '%LLC%'
            OR l.licensee LIKE '%L.L.C.%'
            OR l.licensee LIKE '%Limited%'
            OR l.licensee LIKE '%Company%'
            OR l.licensee LIKE '%Inc%'
        )
        ORDER BY oc.project_count ASC, l.capacity_mw DESC
    """
    results = query_db(query)
    return jsonify(results)


@app.route('/api/diagnostic/data', methods=['GET'])
def get_diagnostic_data():
    """
    Diagnostic endpoint to verify data from both FERC and EIA databases.
    Shows raw data and matching status.
    """
    diagnostic = {}

    # FERC data
    ferc_query = """
        SELECT
            project_number,
            project_name,
            state,
            capacity_mw,
            expiration_date
        FROM licensing_status
        ORDER BY capacity_mw DESC
    """
    diagnostic['ferc_data'] = {
        'count': query_db("SELECT COUNT(*) as count FROM licensing_status", one=True)['count'],
        'records': query_db(ferc_query)
    }

    # EIA data
    eia_query = """
        SELECT
            plant_id,
            plant_name,
            state,
            nameplate_capacity_mw,
            operational_status
        FROM operational_status
        ORDER BY nameplate_capacity_mw DESC
        LIMIT 20
    """
    diagnostic['eia_data'] = {
        'count': query_db("SELECT COUNT(*) as count FROM operational_status", one=True)['count'],
        'top_20_records': query_db(eia_query)
    }

    # Match status
    match_query = """
        SELECT
            m.match_id,
            m.ferc_project_number,
            f.project_name as ferc_name,
            m.eia_plant_id,
            e.plant_name as eia_name,
            m.match_score,
            m.match_status,
            m.match_confidence,
            f.state,
            f.capacity_mw as ferc_capacity,
            e.nameplate_capacity_mw as eia_capacity
        FROM ferc_eia_matches m
        LEFT JOIN licensing_status f ON m.ferc_project_number = f.project_number
        LEFT JOIN operational_status e ON m.eia_plant_id = e.plant_id
        ORDER BY m.match_score DESC
    """
    diagnostic['matches'] = {
        'total': query_db("SELECT COUNT(*) as count FROM ferc_eia_matches", one=True)['count'],
        'by_status': query_db("""
            SELECT match_status, COUNT(*) as count
            FROM ferc_eia_matches
            GROUP BY match_status
        """),
        'records': query_db(match_query)
    }

    # Verification status
    diagnostic['verification'] = {
        'verified_matches': query_db("SELECT COUNT(*) as count FROM ferc_eia_matches WHERE match_status = 'verified'", one=True)['count'],
        'auto_matches': query_db("SELECT COUNT(*) as count FROM ferc_eia_matches WHERE match_status = 'auto'", one=True)['count'],
        'pending_matches': query_db("SELECT COUNT(*) as count FROM ferc_eia_matches WHERE match_status = 'pending'", one=True)['count'],
        'rejected_matches': query_db("SELECT COUNT(*) as count FROM ferc_eia_matches WHERE match_status = 'rejected'", one=True)['count'],
    }

    return jsonify(diagnostic)


@app.route('/api/diagnostic/verify-match/<int:match_id>', methods=['POST'])
def diagnostic_verify_match(match_id):
    """Verify a specific match by ID (diagnostic endpoint)."""
    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE ferc_eia_matches
            SET match_status = 'verified',
                verified_by = 'api',
                verified_date = CURRENT_TIMESTAMP
            WHERE match_id = ?
        """, (match_id,))

        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'message': f'Match {match_id} verified successfully'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/diagnostic/verify-all-pending', methods=['POST'])
def verify_all_pending():
    """Verify all pending matches."""
    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE ferc_eia_matches
            SET match_status = 'verified',
                verified_by = 'api',
                verified_date = CURRENT_TIMESTAMP
            WHERE match_status = 'pending'
        """)

        affected = cursor.rowcount
        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'message': f'Verified {affected} pending matches'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/matches/<int:match_id>/verify', methods=['POST'])
def verify_match(match_id):
    """
    Verify or reject a specific match.

    POST body: {
        "approved": true/false,
        "notes": "optional notes"
    }
    """
    try:
        data = request.get_json()
        approved = data.get('approved', True)
        notes = data.get('notes', '')

        conn = get_db()
        cursor = conn.cursor()

        if approved:
            cursor.execute("""
                UPDATE ferc_eia_matches
                SET match_status = 'verified',
                    verified_by = 'manual',
                    verified_date = CURRENT_TIMESTAMP,
                    verification_notes = ?
                WHERE match_id = ?
            """, (notes, match_id))
        else:
            cursor.execute("""
                UPDATE ferc_eia_matches
                SET match_status = 'rejected',
                    verified_by = 'manual',
                    verified_date = CURRENT_TIMESTAMP,
                    verification_notes = ?
                WHERE match_id = ?
            """, (notes, match_id))

        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'match_id': match_id,
            'status': 'verified' if approved else 'rejected'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================================================
# ANALYTICS ENDPOINTS
# ============================================================================

@app.route('/api/analytics/overview', methods=['GET'])
def get_analytics_overview():
    """
    Get comprehensive analytics data for dashboard charts.
    Returns aggregated statistics for visualizations.
    """
    try:
        conn = get_db()
        cursor = conn.cursor()

        analytics = {}

        # 1. Private Dam Distribution by State (Top 10)
        cursor.execute("""
            SELECT state, COUNT(*) as count
            FROM licensing_status
            WHERE ownership_type = 'Private'
            GROUP BY state
            ORDER BY count DESC
            LIMIT 10
        """)
        analytics['private_by_state'] = [
            {'state': row[0], 'count': row[1]}
            for row in cursor.fetchall()
        ]

        # 2. Operational Status Breakdown
        cursor.execute("""
            SELECT operational_status, COUNT(*) as count
            FROM operational_status
            WHERE operational_status IS NOT NULL
            GROUP BY operational_status
            ORDER BY count DESC
        """)
        analytics['operational_status'] = [
            {'status': row[0], 'count': row[1]}
            for row in cursor.fetchall()
        ]

        # 3. Ownership Type Distribution (All FERC)
        cursor.execute("""
            SELECT ownership_type, COUNT(*) as count
            FROM licensing_status
            WHERE ownership_type IS NOT NULL
            GROUP BY ownership_type
            ORDER BY count DESC
        """)
        analytics['ownership_distribution'] = [
            {'type': row[0], 'count': row[1]}
            for row in cursor.fetchall()
        ]

        # 4. Capacity Distribution (binned)
        cursor.execute("""
            SELECT
                CASE
                    WHEN capacity_mw < 1 THEN '< 1 MW'
                    WHEN capacity_mw < 10 THEN '1-10 MW'
                    WHEN capacity_mw < 50 THEN '10-50 MW'
                    WHEN capacity_mw < 100 THEN '50-100 MW'
                    WHEN capacity_mw < 500 THEN '100-500 MW'
                    ELSE '500+ MW'
                END as capacity_range,
                COUNT(*) as count
            FROM licensing_status
            WHERE capacity_mw IS NOT NULL
            GROUP BY capacity_range
            ORDER BY
                CASE capacity_range
                    WHEN '< 1 MW' THEN 1
                    WHEN '1-10 MW' THEN 2
                    WHEN '10-50 MW' THEN 3
                    WHEN '50-100 MW' THEN 4
                    WHEN '100-500 MW' THEN 5
                    WHEN '500+ MW' THEN 6
                END
        """)
        analytics['capacity_distribution'] = [
            {'range': row[0], 'count': row[1]}
            for row in cursor.fetchall()
        ]

        # 5. License Expiration Urgency (calculated)
        cursor.execute("""
            SELECT
                CASE
                    WHEN julianday(expiration_date) - julianday('now') < 365 THEN 'Critical'
                    WHEN julianday(expiration_date) - julianday('now') < 1095 THEN 'Near-term'
                    WHEN julianday(expiration_date) - julianday('now') < 1825 THEN 'Mid-term'
                    ELSE 'Long-term'
                END as urgency,
                COUNT(*) as count
            FROM licensing_status
            WHERE expiration_date IS NOT NULL
            GROUP BY urgency
            ORDER BY
                CASE urgency
                    WHEN 'Critical' THEN 1
                    WHEN 'Near-term' THEN 2
                    WHEN 'Mid-term' THEN 3
                    WHEN 'Long-term' THEN 4
                END
        """)
        analytics['expiration_urgency'] = [
            {'urgency': row[0], 'count': row[1]}
            for row in cursor.fetchall()
        ]

        # 6. Top 10 States Overall (FERC + EIA combined)
        cursor.execute("""
            SELECT state, COUNT(*) as count
            FROM (
                SELECT state FROM licensing_status
                UNION ALL
                SELECT state FROM operational_status
            )
            WHERE state IS NOT NULL
            GROUP BY state
            ORDER BY count DESC
            LIMIT 10
        """)
        analytics['top_states'] = [
            {'state': row[0], 'count': row[1]}
            for row in cursor.fetchall()
        ]

        # 7. Match Confidence Distribution
        cursor.execute("""
            SELECT match_confidence, COUNT(*) as count
            FROM ferc_eia_matches
            WHERE match_confidence IS NOT NULL
            GROUP BY match_confidence
            ORDER BY
                CASE match_confidence
                    WHEN 'high' THEN 1
                    WHEN 'medium' THEN 2
                    WHEN 'low' THEN 3
                END
        """)
        analytics['match_confidence'] = [
            {'confidence': row[0], 'count': row[1]}
            for row in cursor.fetchall()
        ]

        conn.close()

        return jsonify(analytics)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# =============================================================================
# Error Handlers
# =============================================================================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return jsonify({'error': 'Endpoint not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    return jsonify({'error': 'Internal server error'}), 500


# =============================================================================
# Main
# =============================================================================

if __name__ == '__main__':
    print("="*70)
    print("HYDROPAGE API SERVER")
    print("="*70)
    print(f"Database: {app.config['DATABASE']}")
    print(f"Starting server on http://localhost:5000")
    print("="*70)
    print("\nAvailable endpoints:")
    print("  GET /api/health               - Health check")
    print("  GET /api/stats                - System statistics")
    print("  GET /api/stats/states         - State-level statistics")
    print("  GET /api/plants               - List plants")
    print("  GET /api/plants/<id>          - Plant details")
    print("  GET /api/plants/search        - Search plants")
    print("  GET /api/matches/pending      - Pending matches")
    print("  GET /api/analysis/inoperable  - Inoperable plants")
    print("  GET /api/analysis/reactivation- Reactivation candidates")
    print("  GET /api/analysis/relicensing - Relicensing urgency")
    print("="*70 + "\n")

    app.run(debug=True, host='0.0.0.0', port=5000)
