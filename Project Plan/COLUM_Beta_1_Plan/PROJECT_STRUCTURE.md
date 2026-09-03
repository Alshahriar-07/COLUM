# COLUM Beta 1 Project Structure

COLUM/
├── app/
│   ├── main.py
│   └── lifecycle.py
├── brain/
│   ├── openrouter.py
│   ├── model_selector.py
│   ├── planner.py
│   └── prompts/
├── agent/
│   ├── orchestrator.py
│   ├── task_manager.py
│   └── executor.py
├── voice/
│   ├── wakeword.py
│   ├── listener.py
│   ├── stt.py
│   ├── tts.py
│   └── activity_timer.py
├── vision/
│   ├── screenshot.py
│   ├── ocr.py
│   └── analyzer.py
├── tools/
│   ├── registry.py
│   ├── apps.py
│   ├── windows.py
│   ├── mouse.py
│   ├── keyboard.py
│   ├── files.py
│   ├── terminal.py
│   └── browser.py
├── memory/
│   ├── working.py
│   └── long_term.py
├── workspace/
│   └── manager.py
├── security/
│   ├── policy.py
│   ├── confirmation.py
│   └── audit.py
├── ui/
│   ├── main_window/
│   ├── floating_orb/
│   └── dashboard/
├── config/
│   └── config.example.yaml
├── tests/
├── docs/
└── data/
    ├── cache/
    ├── logs/
    └── memory/
