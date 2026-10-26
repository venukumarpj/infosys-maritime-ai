# Milestone 1: User Authentication Module
**Program:** Infosys Springboard Internship 7.0 (Batch 4)  
**Project:** Agentic AI for Maritime Freight Pricing & Route Optimization  

## Overview
Milestone 1 establishes the secure authentication, authorization, and administrative foundation for the platform. It features robust user management, institutional email validation, session handling via JSON Web Tokens (JWT), dual password recovery channels, and a protected system admin view.

## Tech Stack
* **Frontend/UI:** Streamlit (with custom Deep Ocean theme)
* **Backend & Database:** Python, SQLite
* **Security & Auth:** PyJWT, Custom Regex Validation
* **Notification System:** Gmail SMTP (via Google App Passwords)
* **Tunneling & Deployment:** ngrok, Google Colab

## Key Features Built
1. **Secure Sign In & JWT Sessions:** Issues signed tokens upon successful verification and restricts dashboard access.
2. **Operator Signup:** Enforces uniqueness constraints, strict password complexity rules, and institutional email validation (`@saec.ac.in`).
3. **Dual Password Recovery Flow:** 
   * *Security Question route* (Answer verification)
   * *Email OTP route* (Secure 6-digit code dispatch via Gmail SMTP)
4. **User & Admin Dashboards:** Dedicated workspace for operators and a secure admin portal to view registered users without exposing credentials.

## How to Run
1. Open the notebook in Google Colab.
2. Configure your keys (`JWT_SECRET`, `NGROK_AUTHTOKEN`, `EMAIL_ADDRESS`, `EMAIL_PASSWORD`) in **Colab Secrets** (Key icon on the left sidebar).
3. Run all cells sequentially.
4. Access the public URL provided by ngrok.

## Screenshots
| Login Page | Signup Page |
| :---: | :---: |
| ![Login](https://raw.githubusercontent.com/venukumarpj/infosys-maritime-ai/refs/heads/main/Milestone1/screenshots/Login%20Page.png) | ![Signup](screenshots/signup.png) |

| Forgot Password (OTP) | User Dashboard |
| :---: | :---: |
| ![OTP](screenshots/forgot_password.png) | ![Dashboard](screenshots/dashboard.png) |
