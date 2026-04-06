# Gesture-Based Interaction System (MediaPipe)

This project is a gesture-based interactive system developed for the CS449 Human-Computer Interaction course. It enables users to control a graphical interface using real-time hand gestures via a webcam.

## Overview

The system uses MediaPipe and OpenCV to detect hand landmarks and interpret gestures in real time. These gestures are mapped to user interface actions such as cursor movement, clicking, scrolling, and exiting the application.

The project demonstrates how natural hand movements can be used as an alternative interaction method for GUI systems.

## Features

- Real-time hand tracking using webcam
- Gesture-based cursor control
- Click interaction using pinch gesture
- Scroll functionality using multi-finger gestures
- Quit command using hand gesture
- Visual feedback for user interactions
- Interactive GUI (Fruit Orchard game)

## Gesture Mapping

| Gesture | Description | Function |
|--------|------------|----------|
| One Finger (Index) | Index finger extended | Cursor movement / scroll |
| Two Fingers (Index + Middle) | Two fingers extended | Selection / interaction |
| Pinch (Thumb + Index) | Fingers close together | Click |
| Open Hand | All fingers extended | Stop / toggle |
| Three Fingers | Index + middle + ring | Exit application |

## Technologies Used

- Python
- MediaPipe
- OpenCV
- Tkinter (GUI)

## Implementation Details

- Hand landmarks are detected using MediaPipe’s hand tracking module (21 key points).
- Finger states are determined using relative landmark positions.
- Cursor position is mapped from normalized coordinates to screen space.
- Gestures are recognized based on finger combinations and distance thresholds.
- The system runs in a real-time loop processing webcam frames continuously.

## Contributors

This project was developed as a team effort by:

- Erdem Özcan
- Zeki Karamuk
- Mustafa Adnan Arasan
- İlyas Yeşilyaprak
