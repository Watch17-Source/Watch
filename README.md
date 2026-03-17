# WATCH: Wireless Alarm and Threat-Check Hub for Classrooms

This repository contains the source files for **WATCH**, a LAN-based classroom intrusion detection and alerting system developed for nighttime school security.

## Repository Contents
- **Server-side files** – local web server and dashboard for monitoring alerts
- **Device-side files** – MicroPython code for the ESP32-based classroom unit
- **3D model files** – enclosure design for the device

## Purpose
This repository is intended to serve as a reference for **future researchers** who may continue, improve, or expand the WATCH system. The project was designed to detect intrusion-related movement, send alerts to a local dashboard, and support room-based monitoring without requiring internet access.

## Notes for Future Researchers
Before modifying the system, make sure to review:
- the communication between the **ESP32 device** and the **local server**
- the alert and acknowledgement flow
- the hardware connections and enclosure design
- possible improvements in sensor selection, detection speed, and false-alarm reduction

## Credit
**Lucky Steven Cliff Altubar**  
Proponent of the research and programmer of the system.

## Research Title
**WATCH: Wireless Alarm and Threat-Check Hub for Classrooms**
