# COLUM Beta 1 Installation Plan

## Installer Responsibilities

The Windows installer should:
1. install COLUM files
2. create/update local configuration
3. provide OpenRouter API key setup
4. configure optional Windows startup
5. create desktop/start-menu shortcuts
6. initialize local data directory
7. provide microphone permissions guidance

## First Run

1. Launch COLUM.
2. Configure OpenRouter key.
3. Select/verify free model mode.
4. Configure STT/TTS.
5. Test microphone.
6. Test wake word.
7. Test a harmless command.
8. Confirm standby timeout.
9. Finish setup.

## Startup
COLUM should start a lightweight background runtime rather than loading an expensive model locally.
