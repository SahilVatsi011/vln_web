"""
Smart API endpoints for real-time robot intelligence.
Exposes internal robot state, predictions, and system metrics.
"""

import json
import os
import psutil
from flask import Blueprint, jsonify

smart_api = Blueprint('smart_api', __name__)

# File paths for robot state
STATE_FILE = "/tmp/vln_state.json"
CONVERSATION_FILE = "/tmp/vln_conversation.json"

@smart_api.route('/api/robot_state')
def robot_state():
    """
    Get current robot state including step count, turn count,
    pending actions, and progress.
    """
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                state = json.load(f)
        else:
            # Default state when file doesn't exist
            state = {
                'step_count': 0,
                'max_steps': 120,
                'turn_count': 0,
                'max_turns': 40,
                'pending_actions': [],
                'done': False,
                'current_instruction': '',
                'last_action': None,
            }
        
        # Calculate derived metrics
        steps_remaining = state['max_steps'] - state['step_count']
        turns_remaining = state['max_turns'] - state['turn_count']
        progress_percent = (state['step_count'] / state['max_steps']) * 100
        
        # Add warnings
        warnings = []
        if steps_remaining <= 20 and not state['done']:
            warnings.append({
                'type': 'low_steps',
                'message': f'Only {steps_remaining} steps remaining',
                'severity': 'warning' if steps_remaining > 10 else 'critical'
            })
        
        if turns_remaining <= 5:
            warnings.append({
                'type': 'low_turns',
                'message': f'Only {turns_remaining} LLM calls left',
                'severity': 'warning' if turns_remaining > 2 else 'critical'
            })
        
        return jsonify({
            **state,
            'steps_remaining': steps_remaining,
            'turns_remaining': turns_remaining,
            'progress_percent': round(progress_percent, 1),
            'warnings': warnings,
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@smart_api.route('/api/conversation')
def conversation_history():
    """
    Get conversation history with robot including all turns,
    instructions, and responses.
    """
    try:
        if os.path.exists(CONVERSATION_FILE):
            with open(CONVERSATION_FILE, 'r') as f:
                conversation = json.load(f)
        else:
            conversation = {'turns': []}
        
        return jsonify(conversation)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@smart_api.route('/api/system_metrics')
def system_metrics():
    """
    Get system performance metrics including CPU, memory,
    and GPU stats (if available).
    """
    try:
        metrics = {
            'cpu_percent': psutil.cpu_percent(interval=0.1),
            'memory_percent': psutil.virtual_memory().percent,
            'memory_available_gb': round(psutil.virtual_memory().available / (1024**3), 2),
        }
        
        # Try to get GPU metrics (requires GPUtil)
        try:
            import GPUtil
            gpus = GPUtil.getGPUs()
            if gpus:
                gpu = gpus[0]
                metrics['gpu'] = {
                    'temperature': gpu.temperature,
                    'load_percent': round(gpu.load * 100, 1),
                    'memory_percent': round(gpu.memoryUtil * 100, 1),
                    'memory_used_mb': round(gpu.memoryUsed, 0),
                    'memory_total_mb': round(gpu.memoryTotal, 0),
                }
        except ImportError:
            metrics['gpu'] = None
        
        # Try to get CPU temperature (Linux only)
        try:
            temps = psutil.sensors_temperatures()
            if 'coretemp' in temps:
                metrics['cpu_temp'] = temps['coretemp'][0].current
            elif 'cpu_thermal' in temps:
                metrics['cpu_temp'] = temps['cpu_thermal'][0].current
            else:
                metrics['cpu_temp'] = None
        except (AttributeError, KeyError):
            metrics['cpu_temp'] = None
        
        # Generate warnings
        warnings = []
        if metrics.get('gpu') and metrics['gpu']['temperature'] > 80:
            warnings.append({
                'type': 'high_gpu_temp',
                'message': f"GPU temperature high: {metrics['gpu']['temperature']}°C",
                'severity': 'warning' if metrics['gpu']['temperature'] < 85 else 'critical'
            })
        
        if metrics['memory_percent'] > 90:
            warnings.append({
                'type': 'high_memory',
                'message': f"Memory usage high: {metrics['memory_percent']}%",
                'severity': 'critical'
            })
        
        metrics['warnings'] = warnings
        
        return jsonify(metrics)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@smart_api.route('/api/suggestions')
def get_suggestions():
    """
    Get intelligent suggestions for next actions based on
    current robot state and context.
    """
    try:
        # Load current state
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                state = json.load(f)
        else:
            return jsonify({'suggestions': []})
        
        suggestions = []
        
        # Mission complete suggestions
        if state.get('done'):
            suggestions = [
                {
                    'text': 'Explore the area',
                    'voice_command': 'explore around',
                    'icon': '🔍',
                    'priority': 'high'
                },
                {
                    'text': 'Return to start',
                    'voice_command': 'go back to start',
                    'icon': '🏠',
                    'priority': 'medium'
                },
                {
                    'text': 'Give new instruction',
                    'voice_command': 'new instruction',
                    'icon': '📝',
                    'priority': 'high'
                }
            ]
        
        # Low budget suggestions
        elif state['step_count'] > state['max_steps'] * 0.8:
            suggestions = [
                {
                    'text': 'Complete mission quickly',
                    'voice_command': 'finish quickly',
                    'icon': '⚡',
                    'priority': 'high'
                },
                {
                    'text': 'Return to start',
                    'voice_command': 'return to start',
                    'icon': '🏠',
                    'priority': 'medium'
                },
                {
                    'text': 'Pause and resume later',
                    'voice_command': 'pause',
                    'icon': '⏸️',
                    'priority': 'low'
                }
            ]
        
        # No pending actions
        elif len(state.get('pending_actions', [])) == 0 and not state.get('done'):
            suggestions = [
                {
                    'text': 'Continue forward',
                    'voice_command': 'move forward',
                    'icon': '⬆️',
                    'priority': 'medium'
                },
                {
                    'text': 'Look around',
                    'voice_command': 'turn around',
                    'icon': '👀',
                    'priority': 'low'
                },
                {
                    'text': 'Wait for instruction',
                    'voice_command': 'wait',
                    'icon': '⏳',
                    'priority': 'low'
                }
            ]
        
        return jsonify({'suggestions': suggestions})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
