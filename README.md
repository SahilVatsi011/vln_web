# VLN Web UI

Voice-enabled web interface for robot navigation.

## Quick Start

### Install Dependencies
```bash
pip3 install flask opencv-python psutil
```

### Run Web UI
```bash
cd vln_web
python3 -m vln_web --port 5001
```

### Access
```
http://localhost:5001
```

## On Robot

### SSH to Robot
```bash
ssh chitti@100.91.187.103
# Password: 123456
```

### Start Robot Inference
```bash
cd VLN-DAPO-main
python3 infer.py --checkpoint_path checkpoints/Qwen2.5-VL-3B_rl_rxr_4000_step350
```

### Start Web UI (New Terminal)
```bash
cd vln_web
python3 -m vln_web --port 5001
```

### Access from Browser
```
http://100.91.187.103:5001
```

## Usage

### Voice Command
1. Click microphone button
2. Speak instruction
3. Say "yes" to confirm

### Text Command
1. Type instruction
2. Click "Set" button

### Voice Queries
- "How many steps left?"
- "What's the progress?"
- "What should I do?"

## Features

- Voice control
- Mobile responsive
- Smart suggestions
- Real-time monitoring
- Ambient UI

## Ports

- Web UI: `5001`
- Robot: `100.91.187.103`
