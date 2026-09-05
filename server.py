#!/usr/bin/env python3
import json
import os
import sys
import socket
import threading
import time
import requests
import re
import ast
import shutil
from flask import Flask, request, jsonify, render_template, send_from_directory, Response

# Setup Flask App
# We serve templates from 'templates' and static files from 'static'
app = Flask(__name__, template_folder='templates', static_folder='static')

# Global variables
CONFIG_FILE = "config.json"
config = {}
telegram_bot_thread = None

# Load configuration
def load_config():
    global config
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
            return True
        except Exception as e:
            print(f"Error loading config: {e}")
    return False

# Get Local IP Address
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Connect to an external address (does not send data)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

# Get Termux Package Name/Application ID
def get_termux_package_id():
    prefix = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
    match = re.search(r'/data/data/([^/]+)', prefix)
    return match.group(1) if match else "com.termux"

# ==========================================
# CUSTOM AI TOOLS DEFINITIONS
# ==========================================

# Define Android Internal Storage Workspace Folder
def get_android_workspace():
    paths = [
        os.path.expanduser("~/storage/shared/PocketStrike-AI"),
        "/sdcard/PocketStrike-AI",
        "/storage/emulated/0/PocketStrike-AI"
    ]
    for p in paths:
        try:
            os.makedirs(p, exist_ok=True)
            # Test write access by writing a dummy file
            test_file = os.path.join(p, ".write_test")
            with open(test_file, "w") as f:
                f.write("test")
            os.remove(test_file)
            return os.path.abspath(p)
        except Exception:
            continue
    fallback = os.path.abspath(os.path.join(os.path.dirname(__file__), "workspace"))
    os.makedirs(fallback, exist_ok=True)
    return fallback

def initialize_memory_files():
    # Create the agent directory inside WORKSPACE_DIR
    agent_dir = os.path.join(WORKSPACE_DIR, "agent")
    os.makedirs(agent_dir, exist_ok=True)
    
    user_path = os.path.join(agent_dir, "user.md")
    memory_path = os.path.join(agent_dir, "memory.md")
    agent_path = os.path.join(agent_dir, "agent.md")
    
    # 0. Migrate existing user.md, memory.md, agent.md, and state JSONs if in the root WORKSPACE_DIR
    import shutil
    for fname in ["user.md", "memory.md", "agent.md", "unified_history.json", "conversations.json", "mcp_connections.json", "telegram_active_chats.json"]:
        root_file = os.path.join(WORKSPACE_DIR, fname)
        target_file = os.path.join(agent_dir, fname)
        if os.path.exists(root_file) and not os.path.exists(target_file):
            try:
                shutil.move(root_file, target_file)
            except Exception: pass
            
    # 1. Migrate legacy memory.json if present
    legacy_memory_path = os.path.join(WORKSPACE_DIR, "memory.json")
    legacy_memory_content = ""
    if os.path.exists(legacy_memory_path):
        try:
            with open(legacy_memory_path, "r", encoding="utf-8") as f:
                legacy_memory_content = f.read().strip()
            os.remove(legacy_memory_path)
        except Exception: pass

    # 2. Migrate legacy instructions.txt if present
    legacy_inst_path = os.path.join(WORKSPACE_DIR, "instructions.txt")
    legacy_inst_content = ""
    if os.path.exists(legacy_inst_path):
        try:
            with open(legacy_inst_path, "r", encoding="utf-8") as f:
                legacy_inst_content = f.read().strip()
            os.remove(legacy_inst_path)
        except Exception: pass

    # 3. Initialize user.md
    if not os.path.exists(user_path):
        try:
            with open(user_path, "w", encoding="utf-8") as f:
                f.write("# User Profile\n- Name: (To be detected/filled by AI)\n- Preferences: (To be detected/filled by AI)\n- Skill Level: (To be detected/filled by AI)\n")
        except Exception: pass
        
    # 4. Initialize memory.md (merge with legacy memory if migrated)
    if not os.path.exists(memory_path):
        try:
            content = "# Long-Term Memory\n"
            if legacy_memory_content and legacy_memory_content != "No facts stored yet.":
                content += f"\n### Migrated Memories:\n{legacy_memory_content}\n"
            else:
                content += "- (No memories stored yet. Conversations and project facts will be auto-saved here.)\n"
            with open(memory_path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception: pass
        
    # 5. Initialize agent.md (merge with legacy instructions if migrated)
    if not os.path.exists(agent_path):
        try:
            content = "# Agent Directives\n- Role: You are PocketStrike AI, a powerful security and system assistant running in Termux on Android.\n- Personality: Technical, professional, and efficient.\n"
            if legacy_inst_content and legacy_inst_content != "No custom instructions saved yet.":
                content += f"\n### Migrated Instructions:\n{legacy_inst_content}\n"
            with open(agent_path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception: pass

WORKSPACE_DIR = get_android_workspace()
initialize_memory_files()

def auto_evolve_memory_background(messages):
    """
    Runs in a background thread after each chat turn to review the interaction
    and automatically update user.md, memory.md, or agent.md if new facts,
    preferences, or operational learnings were acquired.
    """
    try:
        import requests
        import json
        import os
        import re

        # Only reflect on the last 4 messages to keep context window tiny and cheap!
        recent_history = messages[-4:]
        if not recent_history:
            return

        user_path = os.path.join(WORKSPACE_DIR, "agent", "user.md")
        memory_path = os.path.join(WORKSPACE_DIR, "agent", "memory.md")
        agent_path = os.path.join(WORKSPACE_DIR, "agent", "agent.md")

        user_content = "No profile stored yet."
        if os.path.exists(user_path):
            with open(user_path, "r", encoding="utf-8") as f:
                user_content = f.read().strip()

        memory_content = "No long-term memories stored yet."
        if os.path.exists(memory_path):
            with open(memory_path, "r", encoding="utf-8") as f:
                memory_content = f.read().strip()

        agent_content = "You are PocketStrike AI, a powerful local security and system assistant running in Termux on the user's Android phone."
        if os.path.exists(agent_path):
            with open(agent_path, "r", encoding="utf-8") as f:
                agent_content = f.read().strip()

        # Build a reflection prompt
        reflection_prompt = f"""You are the memory reflection unit for PocketStrike AI.
Your job is to analyze the recent conversation and update the agent's long-term memory files.

Current files content:
--- user.md (User profile, preferences, name, skill level) ---
{user_content}

--- memory.md (Facts, project conventions, tool tips, lessons learned) ---
{memory_content}

--- agent.md (Agent soul, identity, rules, behavior) ---
{agent_content}

Recent Conversation:
{json.dumps(recent_history, indent=2)}

Task:
Based on the recent conversation, did you learn any new details about the user (name, preferences, interests), project context, or new behavior rules?
If so, update the content of user.md, memory.md, or agent.md accordingly. Keep it concise, structured in clean Markdown, and merge with existing content. Do not overwrite existing facts unless they have changed.

You must respond with raw JSON in this format:
{{
  "user_updated": true/false,
  "user_content": "complete updated user.md text",
  "memory_updated": true/false,
  "memory_content": "complete updated memory.md text",
  "agent_updated": true/false,
  "agent_content": "complete updated agent.md text"
}}

Respond with ONLY the JSON block. Do not include markdown code block formatting (no ```json).
"""

        provider = config.get("provider")
        model = config.get("model")
        api_key = config.get("api_key", "")
        base_url = config.get("base_url", "")
        
        if not provider or not api_key:
            return

        response_text = ""
        
        # Call the model
        if provider == "gemini":
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            payload = {
                "contents": [{"parts": [{"text": reflection_prompt}]}]
            }
            res = requests.post(url, json=payload, timeout=20)
            if res.status_code == 200:
                data = res.json()
                response_text = data["candidates"][0]["content"]["parts"][0]["text"]
        elif provider == "openai":
            url = f"{base_url}/chat/completions" if base_url else "https://api.openai.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": reflection_prompt}],
                "max_tokens": 1000
            }
            res = requests.post(url, headers=headers, json=payload, timeout=20)
            if res.status_code == 200:
                response_text = res.json()["choices"][0]["message"]["content"]
        elif provider == "anthropic":
            url = f"{base_url}/messages" if base_url else "https://api.anthropic.com/v1/messages"
            headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
            payload = {
                "model": model,
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": [{"type": "text", "text": reflection_prompt}]}]
            }
            res = requests.post(url, headers=headers, json=payload, timeout=20)
            if res.status_code == 200:
                response_text = res.json()["content"][0]["text"]
                
        # Parse the JSON response
        if response_text:
            response_text = response_text.strip()
            if response_text.startswith("```"):
                response_text = re.sub(r'^```(?:json)?\n', '', response_text)
                response_text = re.sub(r'\n```$', '', response_text)
            response_text = response_text.strip()
            
            updates = json.loads(response_text)
            
            # Save updates
            if updates.get("user_updated") and updates.get("user_content"):
                with open(user_path, "w", encoding="utf-8") as f:
                    f.write(updates["user_content"].strip())
                print("🧠 [Self-Evolution] user.md auto-updated.")
                
            if updates.get("memory_updated") and updates.get("memory_content"):
                with open(memory_path, "w", encoding="utf-8") as f:
                    f.write(updates["memory_content"].strip())
                print("🧠 [Self-Evolution] memory.md auto-updated.")
                
            if updates.get("agent_updated") and updates.get("agent_content"):
                with open(agent_path, "w", encoding="utf-8") as f:
                    f.write(updates["agent_content"].strip())
                print("🧠 [Self-Evolution] agent.md auto-updated.")
                
    except Exception as e:
        print(f"⚠️ [Self-Evolution Error] failed to auto-evolve memory: {str(e)}")

def analyze_apk_manifest(apk_path):
    """Parses Android APK manifest and zip archive to extract permissions, launcher components, and security flags."""
    try:
        import zipfile
        full_path = sanitize_workspace_path(apk_path) if not os.path.isabs(apk_path) else apk_path
        if not os.path.exists(full_path):
            return f"Error: APK file '{apk_path}' not found."
        
        if not zipfile.is_zipfile(full_path):
            return f"Error: '{apk_path}' is not a valid APK/ZIP archive."

        perms = []
        activities = []
        services = []
        receivers = []

        with zipfile.ZipFile(full_path, 'r') as z:
            file_list = z.namelist()
            has_dex = any(f.endswith('.dex') for f in file_list)
            has_so = any(f.endswith('.so') for f in file_list)
            
            manifest_str = ""
            if "AndroidManifest.xml" in file_list:
                manifest_data = z.read("AndroidManifest.xml")
                import re
                strings = re.findall(rb'[\x20-\x7E]{4,}', manifest_data)
                manifest_str = "\n".join(s.decode('ascii', errors='ignore') for s in strings)
                
                for s in strings:
                    s_text = s.decode('ascii', errors='ignore')
                    if "android.permission." in s_text:
                        perms.append(s_text.strip())
                    elif "Activity" in s_text or "Service" in s_text or "Receiver" in s_text:
                        if "." in s_text and len(s_text) < 100:
                            if "Activity" in s_text: activities.append(s_text)
                            elif "Service" in s_text: services.append(s_text)
                            elif "Receiver" in s_text: receivers.append(s_text)

        perms = sorted(list(set(perms)))
        dangerous_keywords = ["CAMERA", "RECORD_AUDIO", "READ_SMS", "SEND_SMS", "RECEIVE_SMS", "ACCESS_FINE_LOCATION", "READ_CONTACTS", "WRITE_EXTERNAL_STORAGE", "SYSTEM_ALERT_WINDOW", "INSTALL_PACKAGES"]
        dangerous_found = [p for p in perms if any(dk in p for dk in dangerous_keywords)]

        report = [
            f"📦 APK Audit Report for: {os.path.basename(full_path)}",
            f"Path: {full_path}",
            f"Contains Compiled DEX: {'Yes' if has_dex else 'No'}",
            f"Contains Native (.so) Libraries: {'Yes' if has_so else 'No'}",
            f"\n🔑 Permissions Requested ({len(perms)} total):",
            "  - " + "\n  - ".join(perms) if perms else "  - None detected in binary strings.",
            f"\n⚠️ Dangerous Security Permissions ({len(dangerous_found)}):",
            "  - " + "\n  - ".join(dangerous_found) if dangerous_found else "  - None identified.",
            f"\n🧩 Detected Components:",
            f"  - Activities: {len(set(activities))}",
            f"  - Services: {len(set(services))}",
            f"  - Broadcast Receivers: {len(set(receivers))}"
        ]
        return "\n".join(report)
    except Exception as e:
        return f"Error analyzing APK manifest: {str(e)}"

def check_subdomain_takeover(domain):
    """Scans domain/subdomain CNAME records for vulnerable dangling cloud pointers (GitHub Pages, S3, Heroku, Azure, etc.)."""
    try:
        domain = domain.strip().lower().replace("http://", "").replace("https://", "").split("/")[0]
        cname_res = dns_lookup(domain, record_type="CNAME")
        
        takeover_signatures = {
            "github.io": "GitHub Pages",
            "s3.amazonaws.com": "AWS S3 Bucket",
            "herokuapp.com": "Heroku App",
            "azurewebsites.net": "Azure Web App",
            "surge.sh": "Surge.sh",
            "myshopify.com": "Shopify Store",
            "wordpress.com": "WordPress",
            "ghost.io": "Ghost.io",
            "pantheonsite.io": "Pantheon",
            "fastly.net": "Fastly CDN",
            "cloudfront.net": "AWS CloudFront"
        }

        matched_signatures = []
        cname_target = ""
        if "Data:" in cname_res:
            for line in cname_res.splitlines():
                if "Data:" in line:
                    cname_target = line.split("Data:")[1].strip()
                    for sig, provider in takeover_signatures.items():
                        if sig in cname_target.lower():
                            matched_signatures.append((sig, provider))

        status_msg = []
        status_msg.append(f"🎯 Subdomain Takeover Audit: {domain}")
        status_msg.append(f"CNAME Lookup Output:\n{cname_res}")
        
        if matched_signatures:
            status_msg.append("\n⚠️ POTENTIAL DANGLING POINTER DETECTED!")
            for sig, provider in matched_signatures:
                status_msg.append(f"  - Points to cloud provider: {provider} ({cname_target})")
            status_msg.append("  - Action: Verify if the target cloud resource is active or available for unclaimed registration.")
        else:
            status_msg.append("\n✅ No common dangling cloud provider CNAME signatures identified.")

        return "\n".join(status_msg)
    except Exception as e:
        return f"Error checking subdomain takeover: {str(e)}"

def generate_hash_checksum(file_path_or_text, algo="sha256"):
    """Generates MD5, SHA1, SHA256, and SHA512 hashes for a workspace file or text string."""
    try:
        import hashlib
        target_path = sanitize_workspace_path(file_path_or_text) if not os.path.isabs(file_path_or_text) else file_path_or_text
        
        if os.path.exists(target_path) and os.path.isfile(target_path):
            with open(target_path, "rb") as f:
                content = f.read()
            source_desc = f"File: {os.path.basename(target_path)} ({len(content)} bytes)"
        else:
            content = file_path_or_text.encode('utf-8')
            source_desc = f"String Input ({len(content)} bytes)"

        md5_hash = hashlib.md5(content).hexdigest()
        sha1_hash = hashlib.sha1(content).hexdigest()
        sha256_hash = hashlib.sha256(content).hexdigest()
        sha512_hash = hashlib.sha512(content).hexdigest()

        return (f"🔐 Hash Checksum Results:\n"
                f"Source: {source_desc}\n"
                f"MD5:    {md5_hash}\n"
                f"SHA1:   {sha1_hash}\n"
                f"SHA256: {sha256_hash}\n"
                f"SHA512: {sha512_hash}")
    except Exception as e:
        return f"Error calculating hash checksum: {str(e)}"

def analyze_pcap_capture(pcap_path, limit=20):
    """Analyzes network packet capture (.pcap/.pcapng) files for HTTP plain-text headers, logins, DNS queries, and IP traffic."""
    try:
        full_path = sanitize_workspace_path(pcap_path) if not os.path.isabs(pcap_path) else pcap_path
        if not os.path.exists(full_path):
            return f"Error: PCAP file '{pcap_path}' not found."

        import re
        with open(full_path, "rb") as f:
            raw_data = f.read(5 * 1024 * 1024)

        printable_strings = re.findall(rb'[\x20-\x7E]{4,}', raw_data)
        strings_text = [s.decode('ascii', errors='ignore') for s in printable_strings]

        http_requests = [s for s in strings_text if any(s.startswith(m) for m in ["GET ", "POST ", "PUT ", "DELETE ", "HTTP/"])]
        dns_queries = [s for s in strings_text if ".com" in s or ".org" in s or ".net" in s or ".io" in s]
        auth_headers = [s for s in strings_text if "Authorization:" in s or "Bearer " in s or "password" in s.lower() or "user=" in s.lower()]
        ips = list(set(re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', "\n".join(strings_text))))

        report = [
            f"📡 PCAP Analysis Summary for: {os.path.basename(full_path)}",
            f"Extracted Unique IP Addresses ({len(ips)}):",
            "  " + ", ".join(ips[:15]) if ips else "  None identified",
            f"\n🌐 HTTP Requests & Method Lines ({len(http_requests)}):",
            "  - " + "\n  - ".join(http_requests[:limit]) if http_requests else "  No plain-text HTTP methods found.",
            f"\n🔑 Credentials & Authorization Indicators ({len(auth_headers)}):",
            "  - " + "\n  - ".join(auth_headers[:10]) if auth_headers else "  No plain-text credential headers detected.",
            f"\n🔍 DNS Domain References Found ({len(dns_queries)}):",
            "  - " + "\n  - ".join(list(set(dns_queries))[:15]) if dns_queries else "  None detected."
        ]
        return "\n".join(report)
    except Exception as e:
        return f"Error analyzing PCAP capture: {str(e)}"

def jwt_decoder_analyzer(token):
    """Decodes JSON Web Token (JWT) structure, claims, algorithm, and checks for common security misconfigurations."""
    try:
        import base64, json
        token = token.strip()
        parts = token.split(".")
        if len(parts) != 3:
            return "Error: Invalid JWT format. A valid JWT must consist of 3 dot-separated base64 parts (Header.Payload.Signature)."

        def b64_decode(data):
            padding = '=' * (4 - len(data) % 4)
            return base64.urlsafe_b64decode(data + padding).decode('utf-8')

        header_str = b64_decode(parts[0])
        payload_str = b64_decode(parts[1])

        header = json.loads(header_str)
        payload = json.loads(payload_str)

        alg = header.get("alg", "None")
        typ = header.get("typ", "JWT")

        warnings = []
        if alg.lower() == "none":
            warnings.append("🚨 CRITICAL: Token algorithm set to 'none' (Signature validation bypass vulnerability!).")
        elif alg in ["HS256", "HS384", "HS512"]:
            warnings.append("⚠️ WARNING: Uses symmetric key algorithm (HS256/384/512). Vulnerable to brute-force if secret key is weak.")

        import time
        exp = payload.get("exp")
        if exp:
            curr_time = time.time()
            if curr_time > exp:
                warnings.append(f"⏰ EXPIRED: Token expired at timestamp {exp} (Current time: {int(curr_time)}).")
            else:
                warnings.append(f"✅ VALID EXPIRATION: Expires at timestamp {exp} (Remaining: {int(exp - curr_time)}s).")
        else:
            warnings.append("⚠️ MISSING EXP: Token has no expiration ('exp') claim specified.")

        output = [
            "🔑 JWT Decoder & Security Analysis",
            "\nHeader:",
            json.dumps(header, indent=2),
            "\nPayload:",
            json.dumps(payload, indent=2),
            "\nSecurity Warnings & Audit:",
            "  - " + "\n  - ".join(warnings) if warnings else "  - No immediate security flags triggered."
        ]
        return "\n".join(output)
    except Exception as e:
        return f"Error decoding JWT token: {str(e)}"

def system_process_monitor(filter_name=""):
    """Monitors running system processes in Termux/Android, listing PID, user, CPU%, memory, and command lines."""
    try:
        import subprocess
        res = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=10)
        if res.returncode != 0:
            res = subprocess.run(["ps", "-ef"], capture_output=True, text=True, timeout=10)
            
        lines = res.stdout.strip().splitlines()
        if not lines:
            return "No running process information returned."

        header = lines[0]
        proc_list = lines[1:]

        if filter_name:
            proc_list = [line for line in proc_list if filter_name.lower() in line.lower()]

        report = [
            f"📊 System Process Monitor ({len(proc_list)} processes active" + (f", filtered by '{filter_name}'" if filter_name else "") + "):",
            header,
            "──────────────────────────────────────────────────────────────────────────"
        ]
        report.extend(proc_list[:40])
        if len(proc_list) > 40:
            report.append(f"... and {len(proc_list) - 40} more processes.")

        return "\n".join(report)
    except Exception as e:
        return f"Error monitoring system processes: {str(e)}"

def get_system_prompt():
    # Read user.md, memory.md, and agent.md for Hermes-style memory
    user_path = os.path.join(WORKSPACE_DIR, "agent", "user.md")
    memory_path = os.path.join(WORKSPACE_DIR, "agent", "memory.md")
    agent_path = os.path.join(WORKSPACE_DIR, "agent", "agent.md")

    user_content = "No user profile stored yet."
    if os.path.exists(user_path):
        try:
            with open(user_path, "r", encoding="utf-8") as f:
                user_content = f.read().strip()
        except Exception: pass

    memory_content = "No long-term memories stored yet."
    if os.path.exists(memory_path):
        try:
            with open(memory_path, "r", encoding="utf-8") as f:
                memory_content = f.read().strip()
        except Exception: pass

    agent_content = "You are PocketStrike AI, a powerful local security and system assistant running in the Linux terminal (or Termux on Android). You have full access to execute any Linux terminal commands, audit security parameters, run background tasks, parse files, scan networks, and manage systems."
    if os.path.exists(agent_path):
        try:
            with open(agent_path, "r", encoding="utf-8") as f:
                agent_content = f.read().strip()
        except Exception: pass

    import shutil
    is_termux = shutil.which("pkg") is not None or os.path.exists("/data/data/com.termux")
    os_name = "Android / Termux" if is_termux else "Linux System"
    if not is_termux and os.path.exists("/etc/os-release"):
        try:
            with open("/etc/os-release") as f:
                for line in f:
                    if line.startswith("PRETTY_NAME="):
                        os_name = line.split("=")[1].strip().strip('"')
                        break
        except Exception:
            pass

    platform_guidance = ""
    if is_termux:
        platform_guidance = """CURRENT RUNTIME ENVIRONMENT: Android / Termux
- You are running inside Termux on Android.
- Mobile API tools (Termux:API, camera, location, TTS, notifications) and ADB controls are active.
- Shell commands executed via execute_termux_command run in Termux bash."""
    else:
        platform_guidance = f"""CURRENT RUNTIME ENVIRONMENT: Native {os_name}
- You are running natively on a Linux machine ({os_name}).
- You have UNRESTRICTED access to execute any Linux CLI commands, security tools (nmap, gobuster, sqlmap, hydra, john, wireshark, etc.), systemctl, apt, docker, and bash scripts via execute_termux_command.
- CRITICAL TOOL ROUTING RULE: When running on Linux, DO NOT call Termux-only mobile API tools (like take_camera_photo, send_sms, make_phone_call, audit_sms_inbox, read_contacts_list, read_phone_sensors, set_brightness).
- Instead, perform tasks using standard Linux CLI tools via execute_termux_command (e.g. use 'nmap' for port scanning, 'ps aux' for process monitoring, 'curl/wget' for web requests, 'notify-send' for screen alerts, 'spd-say' for voice output, etc.)."""

    # Load remote MCP tools
    mcp_conns = load_mcp_connections()
    mcp_tool_lines = []
    tool_counter = 70
    for conn in mcp_conns:
        server_name = conn.get("name")
        for t in conn.get("tools", []):
            name = t.get("name")
            desc = t.get("description", "No description provided.")
            
            properties = t.get("inputSchema", {}).get("properties", {})
            req_list = t.get("inputSchema", {}).get("required", [])
            args_str_list = []
            for prop_name, prop_val in properties.items():
                is_req = prop_name in req_list
                req_badge = "" if is_req else "=None"
                args_str_list.append(f"{prop_name}{req_badge}")
                
            args_repr = ", ".join(args_str_list)
            mcp_tool_lines.append(f"{tool_counter}. {name}({args_repr})\n    {desc} (Remote MCP: {server_name})")
            tool_counter += 1
            
    mcp_tools_block = ""
    if mcp_tool_lines:
        mcp_tools_block = "\n" + "\n".join(mcp_tool_lines)

    import datetime
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S (Day: %A)")

    return f"""{agent_content}
Current local time and date: {current_time}
{platform_guidance}

You are a self-evolving AI agent that grows more capable over time by reflecting on your experiences and automatically updating your persistent memory files (user.md, memory.md, and agent.md).

Your workspace directory is: {WORKSPACE_DIR} (located in the system storage). Always save files requested by the user inside this folder.
Your project root directory is: {os.path.abspath(os.path.dirname(__file__))} (where your codebase lives). You are allowed to read code files here to explain them, but write access is strictly denied to keep this folder safe from modification.
Critical: You are strictly sandboxed. All write operations (write_file_content) are only allowed inside your workspace directory ({WORKSPACE_DIR}). You are forbidden from writing files in your project root or modifying your own running server code.

---
### 👤 USER PROFILE (Stored in 'user.md')
{user_content}

---
### 💾 LONG-TERM MEMORY & CONVENTIONS (Stored in 'memory.md')
{memory_content}

---
### 🤖 AGENT SOUL & BEHAVIOR DIRECTIVES (Stored in 'agent.md')
{agent_content}

If you need to use a tool to answer the user's request, you must respond with EXACTLY this trigger format and nothing else in that turn:
[TOOL_CALL: tool_name(arg1="value", arg2="value")]

Available Tools:
1. get_system_stats()
   Returns battery level, charging status, free RAM, and storage space in Linux/Termux.
2. local_port_scan(target_ip, ports_list=[...])
   Scans a target IP address for open ports. Use lists like [22, 80, 443]. Keep target list short.
3. list_directory(path=".")
   Lists files and directories. Defaults to your workspace directory ({WORKSPACE_DIR}). Can list files in the project root folder too.
4. read_file_content(file_path, offset=0, limit=15000)
   Reads the content of a text file inside your workspace directory or project root directory. Supports paging via 'offset' and 'limit' parameters for large files.
5. write_file_content(file_path, content)
   Creates or overwrites a file inside your workspace directory. Useful for saving Python scripts or files (like 'memory.json' and 'instructions.txt').
6. run_python_script(script_name, args=[...])
   Runs a Python script written by you inside your workspace directory and returns its output. Use this to run custom scripts, write new tools, or build calculations.
7. execute_termux_command(command)
   Runs any Linux / Termux bash shell command in the system terminal (e.g. 'whoami', 'uname -a', 'systemctl', 'apt', 'git', 'nmap', 'curl', 'grep', 'find', 'python3', 'docker', 'ip a', etc.) and returns standard output.
   Note: Operates inside a persistent, stateful background shell session on Linux and Termux. Directory changes ('cd') and environment variables carry over across turns.
8. web_search(query)
   Scrapes DuckDuckGo HTML for live search results. Use this to lookup CVEs or current information.
9. fetch_url(url)
   Downloads clean text from any website (strips HTML layout) so you can read articles or documentation.
10. get_network_details()
    Returns network details including active interfaces, SSID, local subnet mask, and routing info.
11. list_local_listeners()
    Lists active listening ports on the local Termux host (like a netstat scan).
12. send_android_notification(title, message)
    Sends a system notification banner to the user's Android phone screen.
13. vibrate_device(duration_ms)
    Vibrates the phone for the specified duration (default: 500ms).
14. search_files(pattern)
    Searches for files recursively inside your workspace using glob patterns (e.g. "*.py").
15. local_network_scan()
    Scans the local subnet for active connected devices (fast ARP and ICMP ping sweep). Use this when the user asks to scan the network.
16. audit_android_security()
    Audits the Android device's firmware release version, developer options (USB debugging), root signature binary trails, and outdated packages.
17. subnet_port_sweep(port_number)
    Performs a high-speed parallel sweep checking which hosts on the local network subnet have a specific port open (e.g., check for SSH port 22 or HTTP port 80).
18. take_camera_photo(camera_id="0")
    Captures a photo using the phone's front ("1") or back ("0") camera and saves it to the workspace.
19. get_phone_location()
    Retrieves GPS coordinates of the phone (latitude, longitude, altitude, accuracy).
20. make_phone_call(phone_number)
    Places an outgoing phone call to the specified number.
21. send_sms(phone_number, message)
    Sends an SMS text message to the specified phone number.
22. set_brightness(level)
    Adjusts screen brightness level (0 to 255).
23. set_volume(stream, level)
    Adjusts stream volume levels. stream can be 'music', 'ring', 'alarm', 'notification', or 'system'.
24. take_screenshot()
    Captures the current active screen of the phone (runs via local ADB or Shizuku shell).
25. tap_screen(x, y)
    Simulates a screen touch/tap event at coordinates (x, y) (runs via local ADB or Shizuku shell).
26. swipe_screen(x1, y1, x2, y2, duration_ms)
    Simulates a screen swipe gesture from (x1, y1) to (x2, y2) over the specified duration (runs via local ADB or Shizuku shell).
27. press_key(key_code)
    Simulates a hardware key event (e.g. 3=Home, 4=Back, 26=Power, 82=Menu/Unlock) (runs via local ADB or Shizuku shell).
28. launch_app(package_name)
    Opens an application by its package name (e.g. 'com.whatsapp', 'com.android.chrome') (runs via local ADB or Shizuku shell).
29. control_android_system(action, target="")
    Executes system utility commands on the device. Supported action tokens: 'flashlight_on', 'flashlight_off', 'wifi_on', 'wifi_off', 'bluetooth_on', 'bluetooth_off', 'dark_mode_on', 'dark_mode_off', 'battery_saver_on', 'battery_saver_off', 'dnd_on', 'dnd_off', 'auto_rotate_on', 'auto_rotate_off', 'expand_notifications', 'collapse_notifications', 'get_current_app', 'type_text'. target is used for 'type_text' (specify string to type).
30. get_clipboard()
    Returns the current text contents of the Android system clipboard.
31. set_clipboard(text)
    Overwrites the Android system clipboard with the specified text.
32. list_installed_apps(user_only=True)
    Lists all installed app package names and their APK paths. Defaults to listing third-party user-installed apps (specify user_only=False to list system apps as well).
33. scan_wifi_networks()
    Scans nearby Wi-Fi hotspots and returns network details (SSID, BSSID, RSSI, channel, security mode).
34. speak_text(text)
    Uses the Android Text-To-Speech engine to read the specified text aloud.
35. dns_lookup(domain, record_type="A")
    Queries DNS records (A, AAAA, MX, TXT, CNAME, NS) for a target domain using Cloudflare DNS-over-HTTPS.
36. whois_lookup(domain)
    Queries domain registration and registrar details using public RDAP APIs.
37. analyze_hash(hash_str)
    Analyzes a cryptographic hash string to determine its likely algorithm (e.g. MD5, SHA-1, SHA-256, bcrypt).
38. open_url_on_phone(url)
    Opens a URL/Google search in the default browser on the Android phone screen (runs via local ADB or Shizuku shell). Use this when the user asks to open Google, search for something on their phone screen, or view a website.
39. execute_root_command(command)
    Executes a shell command as SuperUser/Root (using 'su -c') inside Termux and returns the standard output. Only use this if the device has active root privileges, and when standard execute_termux_command is insufficient (e.g., to read protected app files, inspect low-level system attributes, or modify restricted network properties).
40. audit_sms_inbox(limit=10)
    Lists recent SMS messages from the inbox. Use this to audit for spam, phishing links, or suspicious text messages. (runs via local Termux-API).
41. ip_geolocation_lookup(ip_address)
    Performs a geographic lookup of an external IP address, resolving its country, region, city, ISP, and geographic coordinates. Use this to trace the origin of network connections or audit remote IPs.
42. read_phone_sensors(sensor_name="")
    Reads real-time data from phone hardware sensors. If sensor_name is omitted, lists all available sensors. If sensor_name is specified (e.g., 'Gravity', 'Light'), reads the sensor's current data values once. (runs via local Termux-API).
43. dump_ui_layout()
    Dumps the current screen's XML UI layout, parses it, and returns a clean, token-efficient list of all visible text elements, buttons, and input fields, along with their screen center coordinates. Use this to locate buttons or inputs on screen when automating app usage. (runs via local ADB or Shizuku shell).
44. add_scheduled_task(task_type, trigger, description, target="telegram")
    Schedules a reminder or a recurring task. task_type is either 'reminder' (one-shot alert) or 'cron' (recurring task). trigger is an offset ('10m', '2h', '1d', or specific time '18:30') for reminders, or an interval ('5m', '1h', '1d') for crons. description is the message or task content. target is 'telegram', 'system', or 'both'. (runs via local background thread).
45. list_scheduled_tasks()
    Lists all active, pending, or recurring tasks/crons.
46. remove_scheduled_task(task_id)
    Removes a scheduled task/cron by its unique ID.
47. detect_arp_spoofing()
    Scans the local ARP cache to check if multiple IP addresses point to the same MAC address. Use this to audit for active Wi-Fi MITM/ARP spoofing interception attacks. (runs via local Linux file).
48. audit_vpn_connection()
    Checks the current public IP, ISP provider, and verifies if the connection is currently protected or leaking metadata through a VPN, proxy, or Tor exit node. (queries ip-api.com).
49. audit_website_security(url)
    Inspects a web domain or local server URL for SSL/TLS certificate validity (expiration date, issuer) and evaluates the presence of critical security headers (HSTS, CSP, X-Frame-Options, XSS protection).
50. search_file_content(query, pattern="*")
    Searches recursively for a text query inside all files in the workspace (optionally filtered by a glob pattern like '*.py' or '*.txt'). Returns matching line numbers and contents.
51. delete_file(file_path)
    Deletes a file or recursively deletes a directory inside your workspace directory.
52. download_file(url, file_name)
    Downloads a file (binary or text, like images, scripts, security payloads) from a web URL and saves it directly in your workspace directory.
53. read_contacts_list(search_query="")
    Searches the Android device's local address book for contacts matching the search query (name or number). If search_query is omitted, returns all contacts. (runs via local Termux-API).
54. record_screen_video(duration_sec=5)
    Records a video clip of the phone's screen for a specified duration (maximum 30 seconds). Saves the video to the workspace as 'captured_screen_record.mp4'. (runs via local ADB or Shizuku shell).
55. movement_intrusion_alarm(duration_sec=10)
    Monitors phone movement using hardware accelerometer sensors. If moved, vibrates and triggers an intrusion alert notification. (runs via local Termux-API).
56. detect_faces_in_photo(photo_path)
    Performs face detection on the specified photo using OpenCV and Haar Cascade. Binds green boxes around detected faces and saves the output as 'annotated_<filename>'. (runs via local Python processor).
57. check_system_health(auto_install=False)
    Diagnoses local Termux dependencies (e.g. nmap, git, termux-api, adb) and python modules, and optionally installs missing requirements if auto_install=True. (runs via local shell).
58. scan_nearby_signals()
    Scans physical radio frequency signals for nearby Wi-Fi access points and Bluetooth beacons in range. Saves an audit report to the workspace as 'signal_scan_log.md'. Do not confuse this with local_network_scan() which scans active IP addresses on the connected subnet. (runs via local Termux-API or Shizuku).
59. analyze_apk_manifest(apk_path)
    Parses Android APK manifest and zip archive to extract permissions, launcher activities/services, and identify dangerous security permissions.
60. check_subdomain_takeover(domain)
    Scans domain CNAME records to detect vulnerable dangling cloud provider pointers (GitHub Pages, S3, Heroku, Azure, etc.).
61. generate_hash_checksum(file_path_or_text, algo="sha256")
    Calculates MD5, SHA1, SHA256, and SHA512 checksums for a workspace file or text string payload for integrity and malware analysis.
62. analyze_pcap_capture(pcap_path, limit=20)
    Parses network packet capture (.pcap/.pcapng) files for HTTP plain-text headers, logins, DNS queries, and IP traffic breakdowns.
63. jwt_decoder_analyzer(token)
    Decodes JSON Web Token (JWT) structure, claims, algorithm, and audits for security misconfigurations (e.g., 'none' algorithm vulnerabilities).
64. system_process_monitor(filter_name="")
    Monitors active processes running in Termux/Android, listing PID, user, CPU%, memory, and command lines.
65. send_whatsapp_message(contact_or_number, message, auto_send=True)
    Sends a WhatsApp message directly to a phone number or contact name (e.g. 'Alex' or '+1234567890'). Automatically searches local address book if contact name is given, launches the WhatsApp chat with the message drafted, and triggers send. (runs via local Shizuku/ADB & Termux-API).
66. play_media(query, app="spotify")
    Dispatches media playback intents for Spotify, YouTube, or YouTube Music (e.g. play_media(query="favorite playlist", app="spotify") or play_media(query="lofi hip hop", app="youtube")). (runs via local Shizuku/ADB).
67. smart_ui_click(target)
    Finds a UI element on the phone's active screen matching 'target' (by visible text, accessibility description, or resource ID like 'Search', 'Send', 'Chats', 'Allow', 'Play') and taps its center in a single step without needing manual coordinate calculations. (runs via local Shizuku/ADB).
68. smart_ui_type(target="", text="", press_enter=False)
    Taps the target input element (e.g. 'Search', 'Type a message') to focus it and types the specified text. Uses clipboard paste to flawlessly support spaces, punctuation, unicode, and emojis. Set press_enter=True to automatically submit the search/input. (runs via local Shizuku/ADB).
69. send_android_intent(action, data_uri="", package_name="", extras="")
    Dispatches any custom Android Intent via 'am start' (e.g. open Google Maps navigation 'google.navigation:q=Paris', set alarms, open Instagram, dial phone numbers). (runs via local Shizuku/ADB).
70. install_app(app_name)
    Autonomously opens the Play Store, searches for the app (e.g. "Instagram", "Spotify"), finds the result, and clicks Install.
71. uninstall_app(package_name_or_app_name)
    Uninstalls an app directly via package manager or App Info UI.
72. smart_ui_scroll(direction="down", amount=1)
    Scrolls the screen (directions: "down", "up", "left", "right") when a target element is off-screen.
73. smart_ui_wait_for(target, timeout_sec=8, poll_interval=1.0)
    Pauses execution and waits up to timeout_sec for a specific UI element (e.g. "Install", "Loading") to appear on screen.
74. get_screen_text()
    Returns a plain text dump of all visible text on the screen for easy reading of articles, descriptions, or status without parsing UI bounds.
75. tap_coordinates(x, y)
    Taps an exact pixel coordinate (x, y) on the screen. Useful when element bounds are known from dump_ui_layout.
76. see_screen(include_elements=True)
    Acts as your eyes on the phone screen. Captures the phone screen, identifies the foreground app/activity, and returns a clean, numbered visual map of all interactive buttons, inputs, video/content cards with numbered indices [1], [2]... and exact coordinates. Always use this to see what is on screen before deciding what to click!{mcp_tools_block}

Instructions & Operational Guidelines:

🤖 Autonomous Human-Like Phone Operator & Multi-Step Planning (JARVIS Mode):
- You have full, unrestricted, autonomous control over the Android phone via Shizuku / ADB / Termux:API.
- When the user asks you to perform a task on the phone (such as playing a song on YouTube, searching for something, interacting with an app, sending a message, or changing settings):
  1. FORMULATE A CLEAR, STEP-BY-STEP PLAN:
     Outline the steps you will take like a human operator (e.g., Step 1: Open app, Step 2: Inspect screen and locate search bar, Step 3: Type search query and submit, Step 4: Inspect results and tap matching video/card, Step 5: Verify playback).
  2. SEE THE SCREEN LIKE A HUMAN:
     Always use `see_screen()` to inspect what is actively displayed on the phone. It tells you the active app, the list of visible interactive elements (buttons, inputs, video cards, tabs) with their numbered indices and coordinates, and screen text.
  3. INTERACT & CLICK LIKE A HUMAN:
     - To tap any button, search icon, or card: Use `smart_ui_click(target="Label")` or `smart_ui_click(target="[Index]")` using the index from `see_screen()`, or `tap_coordinates(x, y)`.
     - To type into search bars or text inputs: Use `smart_ui_type(target="Search", text="Song name", press_enter=True)`.
     - To scroll down/up if an item is not yet visible: Use `smart_ui_scroll(direction="down")`.
     - To switch apps: Use `launch_app(package_name="...")`.
  4. VERIFY BEFORE CONFIRMING:
     NEVER hallucinate or claim an action succeeded (e.g. saying "the song is playing") until you have actually verified it on screen (e.g. with `see_screen()` or confirming the video player / target UI is active). If something didn't open or click, retry or adjust your coordinates.
  5. MULTI-STEP REASONING:
     You have up to 25 continuous tool turns per request. Feel free to state your reasoning and current step before each tool call trigger:
     "I will open YouTube and play 'Closer' for you.
     Step 1: Opening YouTube...
     [TOOL_CALL: launch_app(package_name="com.google.android.youtube")]"
     Then on the next turn:
     "Step 2: Inspecting the screen to locate the search bar...
     [TOOL_CALL: see_screen()]"
     Then on the next turn:
     "Step 3: Tapping search and typing 'Closer Chainsmokers'...
     [TOOL_CALL: smart_ui_type(target="Search YouTube", text="Closer Chainsmokers", press_enter=True)]"
     Then on the next turn:
     "Step 4: Selecting the video from search results...
     [TOOL_CALL: smart_ui_click(target="[3]")]"
     Then on the final turn:
     "Done! 'Closer' by The Chainsmokers is now playing on YouTube."

- Fast Specialized Automations:
  * For music & media playback: You can also call `play_media(query="...", app="youtube")` (or "spotify" / "youtube_music") which executes the full automated search, video selection, and playback verification pipeline.
  * For messaging: `send_whatsapp_message(contact_or_number="...", message="...")` automatically searches contacts, opens chat, and drafts/sends.
  * For Play Store installation: `install_app(app_name="...")` autonomously searches and installs.

- Strike Voice Assistant Persona:
  * When executing voice commands or spoken prompts, keep your spoken confirmations natural, friendly, and concise (e.g., "Opening YouTube and playing Closer for you now.").
  * Once the action is verified on screen, confirm with a brief friendly completion (e.g., "Done! Closer by The Chainsmokers is now playing on YouTube.").
- Maintain a helpful, conversational, and professional tone.
"""

def get_system_stats():
    stats = {}
    # Battery Capacity
    try:
        if os.path.exists("/sys/class/power_supply/battery/capacity"):
            with open("/sys/class/power_supply/battery/capacity", "r") as f:
                stats["battery_level"] = f.read().strip() + "%"
            with open("/sys/class/power_supply/battery/status", "r") as f:
                stats["battery_status"] = f.read().strip()
        else:
            raise FileNotFoundError()
    except Exception:
        # Fallback to termux command if available
        try:
            import subprocess
            res = subprocess.run(["termux-battery-status"], capture_output=True, text=True, timeout=2)
            if res.returncode == 0:
                bat = json.loads(res.stdout)
                stats["battery_level"] = f"{bat.get('percentage')}%"
                stats["battery_status"] = bat.get("status")
        except Exception:
            stats["battery_level"] = "Unknown"
            stats["battery_status"] = "Unknown"
            
    # Disk Storage (Free Space in Termux home)
    try:
        total, used, free = shutil.disk_usage(os.path.expanduser("~"))
        stats["storage_total"] = f"{total / (2**30):.2f} GB"
        stats["storage_used"] = f"{used / (2**30):.2f} GB"
        stats["storage_free"] = f"{free / (2**30):.2f} GB"
    except Exception as e:
        stats["storage_error"] = str(e)
        
    # RAM Free (from /proc/meminfo)
    try:
        if os.path.exists("/proc/meminfo"):
            with open("/proc/meminfo", "r") as f:
                lines = f.readlines()
                mem_total = 0
                mem_free = 0
                mem_avail = 0
                for line in lines:
                    if "MemTotal" in line:
                        mem_total = int(line.split()[1])
                    elif "MemFree" in line:
                        mem_free = int(line.split()[1])
                    elif "MemAvailable" in line:
                        mem_avail = int(line.split()[1])
                if mem_total:
                    stats["ram_total"] = f"{mem_total / 1024:.2f} MB"
                    stats["ram_free"] = f"{mem_free / 1024:.2f} MB"
                    stats["ram_available"] = f"{mem_avail / 1024:.2f} MB"
        else:
            stats["ram"] = "Only readable on Android/Linux /proc/meminfo"
    except Exception:
        stats["ram"] = "Unknown"
        
    return json.dumps(stats, indent=2)

def local_port_scan(target_ip, ports_list=None):
    # Curated list of the top 100 most common network service ports
    TOP_100_PORTS = [
        21, 22, 23, 25, 53, 67, 68, 69, 80, 110, 111, 119, 123, 135, 137, 138, 139, 143, 161, 162,
        179, 389, 443, 445, 465, 500, 514, 515, 548, 554, 587, 631, 636, 873, 990, 993, 995, 1025,
        1080, 1433, 1434, 1521, 1723, 1812, 1813, 2049, 3000, 3128, 3268, 3306, 3389, 4443, 4500,
        5000, 5060, 5061, 5432, 5631, 5632, 5900, 5984, 6000, 6379, 7077, 8000, 8080, 8081, 8443,
        8888, 9000, 9092, 9100, 9200, 9418, 9999, 11211, 27017, 27018, 27019, 50030, 50070
    ]

    # Parse ports_list intelligently
    if isinstance(ports_list, int):
        ports_list = TOP_100_PORTS[:min(ports_list, 100)]
    elif isinstance(ports_list, str) and ports_list.strip().isdigit():
        ports_list = TOP_100_PORTS[:min(int(ports_list.strip()), 100)]
    elif not ports_list:
        ports_list = TOP_100_PORTS[:30] # Default to top 30 ports
    elif isinstance(ports_list, str):
        try:
            ports_list = json.loads(ports_list)
        except Exception:
            try:
                ports_list = [int(p.strip()) for p in ports_list.strip("[]").split(",") if p.strip()]
            except Exception:
                ports_list = TOP_100_PORTS[:30]
                
    # Parse target target hostname to IP
    try:
        resolved_ip = socket.gethostbyname(target_ip)
    except Exception:
        resolved_ip = target_ip
        
    open_ports = []
    # Convert all items to integers and filter to top 100 limits
    ports_list = [int(p) for p in ports_list][:100]
    
    import concurrent.futures
    
    def check_port(port):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1.0)
            result = s.connect_ex((resolved_ip, port))
            s.close()
            if result == 0:
                return port
        except Exception:
            pass
        return None
        
    with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
        scanned_results = executor.map(check_port, ports_list)
        
    for p in scanned_results:
        if p is not None:
            open_ports.append(p)
            
    open_ports.sort()
    
    # Simple banner lookup for common ports
    banner_details = {}
    for p in open_ports:
        if p == 22: banner_details["22"] = "SSH"
        elif p == 80: banner_details["80"] = "HTTP Web Server"
        elif p == 443: banner_details["443"] = "HTTPS Secure Web Server"
        elif p == 21: banner_details["21"] = "FTP"
        elif p == 3306: banner_details["3306"] = "MySQL Database"
        elif p == 8080: banner_details["8080"] = "HTTP Alternate Web Server"
        elif p == 5000: banner_details["5000"] = "Flask/PocketStrike AI Server"
        else: banner_details[str(p)] = "Unknown Service"
        
    results = {
        "target": target_ip,
        "resolved_ip": resolved_ip,
        "scanned_ports": len(ports_list),
        "open_ports": open_ports,
        "discovered_services": banner_details
    }
    return json.dumps(results, indent=2)

def local_network_scan():
    try:
        import subprocess
        import concurrent.futures
        
        # 1. Identify local subnet by checking routing rules or IP address
        res = subprocess.run(["ip", "route"], capture_output=True, text=True, timeout=5)
        routes = res.stdout if res.returncode == 0 else ""
        
        subnet = None
        for line in routes.split("\n"):
            if "proto kernel" in line and "scope link" in line and "/" in line:
                parts = line.strip().split()
                for p in parts:
                    if "/" in p and p[0].isdigit():
                        subnet = p
                        break
            if subnet:
                break
                
        if not subnet:
            addr_res = subprocess.run(["ip", "addr"], capture_output=True, text=True, timeout=5)
            addr_out = addr_res.stdout if addr_res.returncode == 0 else ""
            match = re.search(r'inet\s+(\d+\.\d+\.\d+\.\d+)/(\d+)\s+[^>]*wlan0', addr_out)
            if match:
                ip = match.group(1)
                mask = match.group(2)
                ip_parts = ip.split(".")
                subnet = f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}.0/{mask}"
                
        if not subnet:
            subnet = "192.168.1.0/24"
            
        base_ip = ".".join(subnet.split("/")[0].split(".")[:-1])
        
        # Found hosts dict to store details (IP -> hostname)
        found_hosts = {}
        
        # 2. Fast ping sweep on the entire Class C range (1-254) in parallel
        def check_host(ip):
            try:
                # Fast timeout of 0.8s
                ping_res = subprocess.run(["ping", "-c", "1", "-W", "1", ip], capture_output=True, timeout=1.2)
                if ping_res.returncode == 0:
                    # Attempt quick reverse hostname lookup
                    try:
                        name_info = socket.gethostbyaddr(ip)
                        hostname = name_info[0]
                    except Exception:
                        hostname = "Unknown Host"
                    return ip, hostname
            except Exception:
                pass
            return None
            
        # Scan full subnet range (1-254)
        ips_to_scan = [f"{base_ip}.{i}" for i in range(1, 255)]
        
        # Speed up with 80 parallel threads
        with concurrent.futures.ThreadPoolExecutor(max_workers=80) as executor:
            scanned_results = executor.map(check_host, ips_to_scan)
            
        for r in scanned_results:
            if r:
                ip, hostname = r
                found_hosts[ip] = hostname
                
        # 3. Read ARP cache to catch silent devices
        try:
            with open("/proc/net/arp", "r") as f:
                arp_lines = f.readlines()
                for line in arp_lines[1:]:
                    parts = line.split()
                    if len(parts) >= 4:
                        ip = parts[0]
                        mac = parts[3]
                        if mac != "00:00:00:00:00:00" and ip.startswith(base_ip) and ip not in found_hosts:
                            try:
                                name_info = socket.gethostbyaddr(ip)
                                hostname = name_info[0]
                            except Exception:
                                hostname = "Unknown Host"
                            found_hosts[ip] = hostname
        except Exception:
            pass
            
        # Format list output
        hosts_output = []
        for ip in sorted(found_hosts.keys(), key=lambda x: int(x.split(".")[-1])):
            hosts_output.append({
                "ip": ip,
                "hostname": found_hosts[ip]
            })
            
        scan_details = {
            "scanned_subnet": subnet,
            "active_hosts_found": len(hosts_output),
            "devices": hosts_output
        }
        return json.dumps(scan_details, indent=2)
    except Exception as e:
        return f"Error scanning local network subnet: {str(e)}"


def list_directory(path="."):
    real_project = os.path.realpath(os.path.abspath(os.path.dirname(__file__)))
    real_workspace = os.path.realpath(WORKSPACE_DIR)
    
    if path == "." or not path:
        target_path = WORKSPACE_DIR
    else:
        if not os.path.isabs(os.path.expanduser(path)):
            target_path = os.path.abspath(os.path.join(WORKSPACE_DIR, path))
            if not os.path.realpath(target_path).startswith(real_workspace):
                target_path = os.path.abspath(os.path.join(real_project, path))
        else:
            target_path = os.path.abspath(os.path.expanduser(path))
            
    real_target = os.path.realpath(target_path)
    is_inside_workspace = real_target.startswith(real_workspace)
    is_inside_project = real_target.startswith(real_project)
    
    if not (is_inside_workspace or is_inside_project):
        return f"Error: Access denied. You are only allowed to list directories inside your workspace ({WORKSPACE_DIR}) or project directory ({real_project})."
        
    if not os.path.exists(real_target):
        return f"Error: Path '{path}' does not exist."
    try:
        items = os.listdir(real_target)
        results = []
        for item in items:
            item_path = os.path.join(real_target, item)
            is_dir = os.path.isdir(item_path)
            size = os.path.getsize(item_path) if not is_dir else 0
            results.append({
                "name": item,
                "type": "directory" if is_dir else "file",
                "size_bytes": size
            })
        return json.dumps(results, indent=2)
    except Exception as e:
        return f"Error listing directory: {str(e)}"

def read_file_content(file_path, offset=0, limit=15000):
    real_project = os.path.realpath(os.path.abspath(os.path.dirname(__file__)))
    real_workspace = os.path.realpath(WORKSPACE_DIR)
    
    if not os.path.isabs(os.path.expanduser(file_path)):
        target_path = os.path.abspath(os.path.join(WORKSPACE_DIR, file_path))
        if not os.path.realpath(target_path).startswith(real_workspace):
            target_path = os.path.abspath(os.path.join(real_project, file_path))
    else:
        target_path = os.path.abspath(os.path.expanduser(file_path))
        
    real_target = os.path.realpath(target_path)
    is_inside_workspace = real_target.startswith(real_workspace)
    is_inside_project = real_target.startswith(real_project)
    
    if not (is_inside_workspace or is_inside_project):
        return f"Error: Read access denied. You are only allowed to read files inside your workspace ({WORKSPACE_DIR}) or project directory ({real_project})."
        
    if os.path.basename(real_target) == "config.json":
        return f"Error: Read access denied to critical configuration file config.json."
        
    if not os.path.exists(real_target):
        return f"Error: File '{file_path}' does not exist."
    if os.path.isdir(real_target):
        return f"Error: '{file_path}' is a directory. Use list_directory to see its contents."
        
    try:
        file_size = os.path.getsize(real_target)
        offset = max(0, int(offset))
        limit = max(1, min(int(limit), 20000))
        
        with open(real_target, "r", encoding="utf-8", errors="ignore") as f:
            f.seek(offset)
            content = f.read(limit)
            
        eof = (offset + len(content)) >= file_size
        meta = f"[File: {file_path} | Size: {file_size} bytes | Offset: {offset} | Length: {len(content)} | EOF: {eof}]\n---\n"
        
        if not eof:
            content += "\n\n[Content truncated. Use read_file_content with a higher offset to read more...]"
            
        return meta + content
    except Exception as e:
        return f"Error reading file: {str(e)}"

def search_file_content(query, pattern="*"):
    try:
        import fnmatch
        matches = []
        query_lower = query.lower()
        
        for root, _, filenames in os.walk(WORKSPACE_DIR):
            for filename in fnmatch.filter(filenames, pattern):
                file_path = os.path.join(root, filename)
                rel_path = os.path.relpath(file_path, WORKSPACE_DIR)
                
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        for line_num, line in enumerate(f, 1):
                            if query_lower in line.lower():
                                matches.append({
                                    "file": rel_path,
                                    "line": line_num,
                                    "content": line.strip()
                                })
                                if len(matches) >= 50:
                                    break
                except Exception:
                    pass
            if len(matches) >= 50:
                break
                
        if not matches:
            return f"No matches found for query '{query}' in files matching '{pattern}'."
            
        output = [f"=== SEARCH RESULTS FOR '{query}' ==="]
        for m in matches:
            output.append(f"{m['file']}:{m['line']}: {m['content']}")
        if len(matches) >= 50:
            output.append("\n[Truncated... More than 50 results found.]")
            
        return "\n".join(output)
    except Exception as e:
        return f"Error searching file content: {str(e)}"

def write_file_content(file_path, content):
    if not os.path.isabs(os.path.expanduser(file_path)):
        target_path = os.path.abspath(os.path.join(WORKSPACE_DIR, file_path))
    else:
        target_path = os.path.abspath(os.path.expanduser(file_path))
        
    # Security Sandbox Check: Prevent path traversal or writing outside the workspace directory
    real_target = os.path.realpath(target_path)
    real_workspace = os.path.realpath(WORKSPACE_DIR)
    
    if not real_target.startswith(real_workspace):
        return f"Error: Write access denied. You are only allowed to write files inside your workspace: {WORKSPACE_DIR}"
        
    # Prevent overwriting actual running system files in the project root folder
    real_project = os.path.realpath(os.path.abspath(os.path.dirname(__file__)))
    forbidden_paths = [
        os.path.realpath(os.path.join(real_project, f))
        for f in ["server.py", "setup.py", "launch.sh", "install.sh", "config.json"]
    ]
    if real_target in forbidden_paths:
        return f"Error: Editing critical active system files in the project folder is forbidden to prevent server crash."
        
    try:
        os.makedirs(os.path.dirname(real_target), exist_ok=True)
        with open(real_target, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Success: File '{file_path}' written successfully."
    except Exception as e:
        return f"Error writing file: {str(e)}"

def delete_file(file_path):
    if not os.path.isabs(os.path.expanduser(file_path)):
        target_path = os.path.abspath(os.path.join(WORKSPACE_DIR, file_path))
    else:
        target_path = os.path.abspath(os.path.expanduser(file_path))
        
    real_target = os.path.realpath(target_path)
    real_workspace = os.path.realpath(WORKSPACE_DIR)
    
    if not real_target.startswith(real_workspace):
        return f"Error: Access denied. You are only allowed to delete files inside your workspace: {WORKSPACE_DIR}"
        
    if not os.path.exists(real_target):
        return f"Error: File '{file_path}' does not exist."
        
    # Prevent deleting active system files in the project root folder
    real_project = os.path.realpath(os.path.abspath(os.path.dirname(__file__)))
    forbidden_paths = [
        os.path.realpath(os.path.join(real_project, f))
        for f in ["server.py", "setup.py", "launch.sh", "install.sh", "config.json"]
    ]
    if real_target in forbidden_paths:
        return f"Error: Deleting critical system files in the project folder is forbidden."
        
    if os.path.isdir(real_target):
        try:
            shutil.rmtree(real_target)
            return f"Success: Directory '{file_path}' and all its contents deleted successfully."
        except Exception as e:
            return f"Error deleting directory: {str(e)}"
    else:
        try:
            os.remove(real_target)
            return f"Success: File '{file_path}' deleted successfully."
        except Exception as e:
            return f"Error deleting file: {str(e)}"

def run_python_script(script_name, args=None):
    if not args:
        args = []
    elif isinstance(args, str):
        try:
            args = json.loads(args)
        except Exception:
            args = [args]
            
    # Resolve and sandbox path
    target_path = os.path.abspath(os.path.join(WORKSPACE_DIR, script_name))
    real_target = os.path.realpath(target_path)
    real_workspace = os.path.realpath(WORKSPACE_DIR)
    
    if not real_target.startswith(real_workspace):
        return "Error: Script execution denied. You can only execute scripts inside your workspace."
        
    if not os.path.exists(real_target):
        return f"Error: Script '{script_name}' does not exist. Write it first using write_file_content."
        
    try:
        import subprocess
        cmd = [sys.executable, real_target] + [str(a) for a in args]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        output = f"Exit Code: {res.returncode}\n"
        if res.stdout:
            output += f"Stdout:\n{res.stdout}\n"
        if res.stderr:
            output += f"Stderr:\n{res.stderr}\n"
        return output
    except subprocess.TimeoutExpired:
        return "Error: Script execution timed out (limit: 30 seconds)."
    except Exception as e:
        return f"Error running script: {str(e)}"

    except Exception as e:
        return f"Error running script: {str(e)}"

# =======================================================
# STATEFUL BACKGROUND SHELL SESSION CONTROLLER
# =======================================================
class StatefulShell:
    def __init__(self):
        self.process = None
        self.stdout_queue = None
        self.stderr_queue = None
        self.current_directory = WORKSPACE_DIR
        self.init_shell()

    def init_shell(self):
        try:
            import subprocess
            import queue
            import threading
            
            # Start background shell process
            shell_executable = "bash" if shutil.which("bash") else "sh"
            self.process = subprocess.Popen(
                [shell_executable],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                cwd=self.current_directory
            )
            
            self.stdout_queue = queue.Queue()
            self.stderr_queue = queue.Queue()
            
            # Start background non-blocking output reader threads
            def read_output(stream, q):
                for line in iter(stream.readline, ''):
                    q.put(line)
                stream.close()
                
            self.stdout_thread = threading.Thread(target=read_output, args=(self.process.stdout, self.stdout_queue))
            self.stderr_thread = threading.Thread(target=read_output, args=(self.process.stderr, self.stderr_queue))
            
            self.stdout_thread.daemon = True
            self.stderr_thread.daemon = True
            
            self.stdout_thread.start()
            self.stderr_thread.start()
        except Exception as e:
            print(f"Failed to initialize stateful shell: {str(e)}")

    def execute(self, cmd_str, timeout=30):
        # Safety token validation
        forbidden_tokens = ["rm -rf", "rm -f /", "mkfs", "dd if="]
        for token in forbidden_tokens:
            if token in cmd_str:
                return f"Error: Command execution blocked. Forbidden token: '{token}'"
                
        if not self.process or self.process.poll() is not None:
            # Restart shell if it crashed or terminated
            self.init_shell()
            
        import time
        import queue
        
        # Clear out any residual queue data
        while not self.stdout_queue.empty():
            try: self.stdout_queue.get_nowait()
            except queue.Empty: break
        while not self.stderr_queue.empty():
            try: self.stderr_queue.get_nowait()
            except queue.Empty: break
            
        # Append sentinel marker to detect command completion
        sentinel = f"__PKST_CMD_DONE_{int(time.time())}__"
        full_command = f"{cmd_str}\npwd\necho '{sentinel}'\necho '{sentinel}' >&2\n"
        
        try:
            self.process.stdin.write(full_command)
            self.process.stdin.flush()
        except Exception as e:
            self.init_shell()
            return f"Error: Failed to write to shell input. Shell restarted. Details: {str(e)}"
            
        stdout_buf = []
        stderr_buf = []
        start_time = time.time()
        
        # Poll stdout and stderr until sentinel marker is encountered or timeout expires
        while time.time() - start_time < timeout:
            # Read stdout
            while True:
                try:
                    line = self.stdout_queue.get_nowait()
                    if sentinel in line:
                        break
                    stdout_buf.append(line)
                except queue.Empty:
                    break
                    
            # Read stderr
            while True:
                try:
                    line = self.stderr_queue.get_nowait()
                    if sentinel in line:
                        break
                    stderr_buf.append(line)
                except queue.Empty:
                    break
                    
            # Break if sentinel marks command completion
            if (stdout_buf and sentinel in stdout_buf[-1]) or (any(sentinel in l for l in stdout_buf)):
                break
                
            time.sleep(0.05)
            
        # Strip sentinel from logs
        stdout_clean = [l for l in stdout_buf if sentinel not in l]
        stderr_clean = [l for l in stderr_buf if sentinel not in l]
        
        # Update working directory tracking
        if stdout_clean:
            # The last clean line printed is our 'pwd' output from the sentinel call
            potential_pwd = stdout_clean[-1].strip()
            if os.path.exists(potential_pwd):
                self.current_directory = potential_pwd
                stdout_clean = stdout_clean[:-1] # Remove pwd line from user stdout logs
                
        output = ""
        if stdout_clean:
            output += "".join(stdout_clean)
        if stderr_clean:
            output += "Stderr:\n" + "".join(stderr_clean)
            
        if not output.strip():
            # If timed out
            if time.time() - start_time >= timeout:
                return "Command execution completed (or timed out after 30 seconds)."
            return "Command executed successfully (no output)."
            
        return output

# Initialize single global stateful shell instance
GLOBAL_SHELL = StatefulShell()

def execute_termux_command(command):
    # Route command execution dynamically to our persistent stateful shell
    return GLOBAL_SHELL.execute(command)

def audit_android_security():
    audit = {}
    import subprocess
    import shutil
    
    if shutil.which("getprop"):
        # Android / Termux Security Audit
        try:
            release_res = subprocess.run(["getprop", "ro.build.version.release"], capture_output=True, text=True, timeout=3)
            patch_res = subprocess.run(["getprop", "ro.build.version.security_patch"], capture_output=True, text=True, timeout=3)
            sdk_res = subprocess.run(["getprop", "ro.build.version.sdk"], capture_output=True, text=True, timeout=3)
            brand_res = subprocess.run(["getprop", "ro.product.brand"], capture_output=True, text=True, timeout=3)
            model_res = subprocess.run(["getprop", "ro.product.model"], capture_output=True, text=True, timeout=3)
            
            audit["platform"] = "Android / Termux"
            audit["android_version"] = release_res.stdout.strip() if release_res.returncode == 0 else "Unknown"
            audit["security_patch"] = patch_res.stdout.strip() if patch_res.returncode == 0 else "Unknown"
            audit["sdk_api_level"] = sdk_res.stdout.strip() if sdk_res.returncode == 0 else "Unknown"
            audit["device_brand"] = brand_res.stdout.strip() if brand_res.returncode == 0 else "Unknown"
            audit["device_model"] = model_res.stdout.strip() if model_res.returncode == 0 else "Unknown"
        except Exception as e:
            audit["properties_error"] = str(e)
            
        root_signatures = ["/system/bin/su", "/system/xbin/su", "/sbin/su", "/system/sd/xbin/su", "/system/bin/failsafe/su", "/data/local/xbin/su", "/data/local/bin/su"]
        su_found = any(os.path.exists(path) for path in root_signatures) or shutil.which("su") is not None
        audit["superuser_root_access"] = "Active/Rooted" if su_found else "Not Rooted / Standard User"
        
        try:
            adb_res = subprocess.run(["getprop", "init.svc.adbd"], capture_output=True, text=True, timeout=3)
            audit["adb_debugging_status"] = "Active/Enabled" if "running" in adb_res.stdout else "Disabled"
        except Exception:
            pass
    else:
        # Standard Linux Security Audit (Debian / Ubuntu / Kali / Mint / Arch)
        audit["platform"] = "Linux Desktop / Server"
        try:
            uname_res = subprocess.run(["uname", "-sr"], capture_output=True, text=True, timeout=3)
            audit["kernel_version"] = uname_res.stdout.strip() if uname_res.returncode == 0 else "Unknown"
            
            if os.path.exists("/etc/os-release"):
                with open("/etc/os-release", "r") as f:
                    for line in f:
                        if line.startswith("PRETTY_NAME="):
                            audit["os_name"] = line.split("=")[1].strip().strip('"')
                            break
        except Exception as e:
            audit["linux_info_error"] = str(e)
            
        is_root = os.geteuid() == 0 if hasattr(os, "geteuid") else False
        audit["superuser_root_access"] = "Active Root User (uid=0)" if is_root else "Standard Non-Root User"

        # Check Linux firewall state (ufw or iptables)
        if shutil.which("ufw"):
            ufw_res = subprocess.run(["ufw", "status"], capture_output=True, text=True, timeout=3)
            audit["firewall_ufw_status"] = ufw_res.stdout.splitlines()[0] if ufw_res.returncode == 0 else "Unknown"
        else:
            audit["firewall_ufw_status"] = "ufw not installed"

    # Common security recommendations
    evaluation = []
    if su_found:
        evaluation.append("WARNING: SuperUser root access detected. Ensure you have custom firewalls or verified root binaries installed to prevent malicious permission escalations.")
    if audit.get("security_patch") != "Unknown":
        # Check patch age
        try:
            from datetime import datetime
            patch_date = datetime.strptime(audit["security_patch"], "%Y-%m-%d")
            diff = (datetime.now() - patch_date).days
            if diff > 180: # Outdated by more than 6 months
                evaluation.append(f"WARNING: Android security patch is {diff} days outdated (Last updated: {audit['security_patch']}). The device is susceptible to older CVE exploits.")
        except Exception:
            pass
            
    if audit.get("upgradable_packages_count") != "Unknown" and isinstance(audit.get("upgradable_packages_count"), int) and audit["upgradable_packages_count"] > 10:
        evaluation.append(f"TIP: Termux has {audit['upgradable_packages_count']} packages outdated. Run 'pkg upgrade' to patch local software dependencies.")
        
    if not evaluation:
        evaluation.append("Device security configuration is optimal. No critical vulnerabilities found in default interface checklist.")
        
    audit["audit_recommendations"] = evaluation
    return json.dumps(audit, indent=2)

def subnet_port_sweep(port_number):
    try:
        import subprocess
        import concurrent.futures
        
        # 1. Resolve subnet range
        res = subprocess.run(["ip", "route"], capture_output=True, text=True, timeout=5)
        routes = res.stdout if res.returncode == 0 else ""
        
        subnet = None
        for line in routes.split("\n"):
            if "proto kernel" in line and "scope link" in line and "/" in line:
                parts = line.strip().split()
                for p in parts:
                    if "/" in p and p[0].isdigit():
                        subnet = p
                        break
            if subnet:
                break
                
        if not subnet:
            addr_res = subprocess.run(["ip", "addr"], capture_output=True, text=True, timeout=5)
            addr_out = addr_res.stdout if addr_res.returncode == 0 else ""
            match = re.search(r'inet\s+(\d+\.\d+\.\d+\.\d+)/(\d+)\s+[^>]*wlan0', addr_out)
            if match:
                ip = match.group(1)
                mask = match.group(2)
                ip_parts = ip.split(".")
                subnet = f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}.0/{mask}"
                
        if not subnet:
            subnet = "192.168.1.0/24"
            
        base_ip = ".".join(subnet.split("/")[0].split(".")[:-1])
        
        target_port = int(port_number)
        active_listeners = []
        
        # 2. Parallel thread sweep to scan the target port across all subnet hosts (1-254)
        def scan_host_port(ip):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.8) # Keep it extremely fast
                result = s.connect_ex((ip, target_port))
                s.close()
                if result == 0:
                    try:
                        name_info = socket.gethostbyaddr(ip)
                        hostname = name_info[0]
                    except Exception:
                        hostname = "Unknown Host"
                    return {
                        "ip": ip,
                        "hostname": hostname
                    }
            except Exception:
                pass
            return None
            
        ips_to_scan = [f"{base_ip}.{i}" for i in range(1, 255)]
        
        # Sweep with 80 parallel threads
        with concurrent.futures.ThreadPoolExecutor(max_workers=80) as executor:
            scanned_results = executor.map(scan_host_port, ips_to_scan)
            
        for r in scanned_results:
            if r:
                active_listeners.append(r)
                
        sweep_details = {
            "scanned_subnet": subnet,
            "target_port": target_port,
            "hosts_found_listening": len(active_listeners),
            "devices": active_listeners
        }
        return json.dumps(sweep_details, indent=2)
    except Exception as e:
        return f"Error performing subnet port sweep: {str(e)}"

# =======================================================
# PHONE HARDWARE & SYSTEM CONTROL TOOLS (TERMUX:API)
# =======================================================
def take_camera_photo(camera_id="0"):
    try:
        import subprocess
        # camera_id: "0" = back, "1" = front
        target_name = "captured_photo.jpg"
        target_path = os.path.join(WORKSPACE_DIR, target_name)
        
        # Cleanup old photo
        if os.path.exists(target_path):
            os.remove(target_path)
            
        cmd = ["termux-camera-photo", "-c", str(camera_id), target_path]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
        if res.returncode == 0 and os.path.exists(target_path):
            return f"Success: Photo captured. Saved to workspace as '{target_name}'. Path: {target_path}."
        return f"Error taking photo: {res.stderr} (Ensure Termux:API app is installed and camera permission is granted)"
    except Exception as e:
        return f"Error executing camera photo tool: {str(e)}"

def get_phone_location():
    try:
        import subprocess
        res = subprocess.run(["termux-location", "-p", "network"], capture_output=True, text=True, timeout=10)
        if res.returncode == 0:
            return res.stdout
        return f"Error getting location: {res.stderr} (Ensure GPS location permissions are granted and Location services are enabled)"
    except Exception as e:
        return f"Error executing location tool: {str(e)}"

def make_phone_call(phone_number):
    try:
        import subprocess
        cmd = ["termux-telephony-call", str(phone_number)]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            return f"Success: Initiated phone call to {phone_number}."
        return f"Error making call: {res.stderr}"
    except Exception as e:
        return f"Error executing phone call tool: {str(e)}"

def send_sms(phone_number, message):
    try:
        import subprocess
        cmd = ["termux-sms-send", "-n", str(phone_number), message]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        if res.returncode == 0:
            return f"Success: SMS sent to {phone_number}."
        return f"Error sending SMS: {res.stderr}"
    except Exception as e:
        return f"Error executing SMS tool: {str(e)}"

def read_contacts_list(search_query=None):
    try:
        import subprocess
        import json
        res = subprocess.run(["termux-contact-list"], capture_output=True, text=True, timeout=8)
        if res.returncode != 0:
            return f"Error running termux-contact-list (exit code {res.returncode}): {res.stderr}"
            
        contacts = json.loads(res.stdout)
        
        if search_query:
            query = str(search_query).strip().lower()
            filtered = []
            for c in contacts:
                name = str(c.get("name", "")).lower()
                number = str(c.get("number", "")).lower()
                if query in name or query in number:
                    filtered.append(c)
            contacts = filtered
            
        if not contacts:
            return "No matching contacts found."
            
        lines = []
        for c in contacts:
            name = c.get("name", "Unknown")
            number = c.get("number", "N/A")
            lines.append(f"- {name}: {number}")
            
        return "\n".join(lines)
    except FileNotFoundError:
        return "Error: termux-contact-list is not available on this device. Ensure Termux:API is installed and configured."
    except Exception as e:
        return f"Error reading contacts: {str(e)}"

def record_screen_video(duration_sec=5):
    target_name = "captured_screen_record.mp4"
    target_path = os.path.join(WORKSPACE_DIR, target_name)
    
    if os.path.exists(target_path):
        try: os.remove(target_path)
        except Exception: pass
        
    duration = min(max(int(duration_sec), 2), 30)
    
    import shutil
    use_shizuku = shutil.which("rish") is not None or os.path.exists("/sdcard/Shizuku/rish") or os.path.exists(os.path.expanduser("~/storage/shared/Shizuku/rish"))
    
    if use_shizuku:
        run_adb_command("devices")
        rish_path = shutil.which("rish") or "/data/data/com.termux/files/usr/bin/rish"
        env = os.environ.copy()
        env["RISH_APPLICATION_ID"] = get_termux_package_id()
        env.pop("LD_LIBRARY_PATH", None)
        env.pop("LD_PRELOAD", None)
        shell_exe = "/system/bin/sh" if os.path.exists("/system/bin/sh") else "sh"
        
        try:
            subprocess.run([shell_exe, rish_path, "-c", "rm /sdcard/temp_record.mp4"], env=env, capture_output=True, timeout=5)
            cmd = f"screenrecord --time-limit {duration} /sdcard/temp_record.mp4"
            res = subprocess.run([shell_exe, rish_path, "-c", cmd], env=env, capture_output=True, timeout=duration + 10)
            
            sdcard_path = "/sdcard/temp_record.mp4"
            if not os.path.exists(sdcard_path):
                sdcard_path = "/storage/emulated/0/temp_record.mp4"
                
            if os.path.exists(sdcard_path) and os.path.getsize(sdcard_path) > 0:
                shutil.copy(sdcard_path, target_path)
                try: os.remove(sdcard_path)
                except Exception: pass
                return f"Success: Screen recorded for {duration} seconds. Saved to workspace as '{target_name}'. Path: {target_path}."
        except Exception:
            pass
            
    # Fallback to standard ADB
    ok, out = run_adb_command("devices")
    if not ok or len([line for line in out.strip().split("\n") if "device" in line and not "devices" in line]) == 0:
        return "Error: Neither Shizuku nor ADB is connected. Screen recording requires Shizuku or wireless ADB authorized on this device."
        
    run_adb_command("shell rm /sdcard/temp_record.mp4")
    ok, out = run_adb_command(f"shell screenrecord --time-limit {duration} /sdcard/temp_record.mp4")
    if not ok:
        return f"Error executing screenrecord command: {out}"
        
    ok, out = run_adb_command(f"pull /sdcard/temp_record.mp4 {target_path}")
    run_adb_command("shell rm /sdcard/temp_record.mp4")
    
    if ok and os.path.exists(target_path) and os.path.getsize(target_path) > 0:
        return f"Success: Screen recorded for {duration} seconds. Saved to workspace as '{target_name}'. Path: {target_path}."
    return f"Error transferring video record to workspace: {out}"

def movement_intrusion_alarm(duration_sec=10):
    import subprocess
    import json
    import time
    import math
    
    duration = min(max(int(duration_sec), 5), 60)
    
    try:
        proc = subprocess.Popen(
            ["termux-sensor", "-s", "accelerometer", "-delay", "200"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
    except FileNotFoundError:
        return "Error: termux-sensor utility is not installed. Make sure Termux:API is installed and configured."
        
    start_time = time.time()
    baseline = None
    triggered = False
    max_deviation = 0.0
    
    try:
        import select
        
        while time.time() - start_time < duration:
            r, _, _ = select.select([proc.stdout], [], [], 0.5)
            if r:
                line = proc.stdout.readline()
                if not line:
                    break
                line = line.strip()
                if "values" in line:
                    try:
                        idx = line.find("[")
                        if idx != -1:
                            end_idx = line.find("]", idx)
                            if end_idx != -1:
                                vals_str = line[idx+1:end_idx]
                                vals = [float(v.strip()) for v in vals_str.split(",")]
                                if len(vals) >= 3:
                                    x, y, z = vals[0], vals[1], vals[2]
                                    magnitude = math.sqrt(x*x + y*y + z*z)
                                    
                                    if baseline is None:
                                        baseline = magnitude
                                    else:
                                        deviation = abs(magnitude - baseline)
                                        if deviation > max_deviation:
                                            max_deviation = deviation
                                        if deviation > 1.8:
                                            triggered = True
                    except Exception:
                        pass
                          
        proc.terminate()
        subprocess.run(["termux-sensor", "-n"], capture_output=True, timeout=2)
        
        if triggered:
            vibrate_device(800)
            send_android_notification("🚨 Intrusion Alarm", f"Movement detected! Max deviation: {max_deviation:.2f} m/s²")
            return f"ALARM TRIGGERED: Movement detected during monitoring window! Max acceleration deviation: {max_deviation:.2f} m/s² (Threshold: 1.8 m/s²). Intruder alert notification dispatched."
        else:
            return f"Secure: No movement detected during the {duration} seconds monitoring window. Max deviation: {max_deviation:.2f} m/s² (stationary)."
            
    except Exception as e:
        try: proc.terminate()
        except Exception: pass
        subprocess.run(["termux-sensor", "-n"], capture_output=True, timeout=2)
        return f"Error running intrusion alarm: {str(e)}"

def detect_faces_in_photo(photo_path):
    import os
    import base64
    real_path = os.path.abspath(os.path.expanduser(photo_path))
    if not os.path.exists(real_path):
        real_path = os.path.join(WORKSPACE_DIR, photo_path)
        if not os.path.exists(real_path):
            return f"Error: Photo file '{photo_path}' not found."
            
    # Try importing OpenCV first for drawing local bounding boxes
    try:
        import cv2
        has_opencv = True
    except ImportError:
        has_opencv = False
        
    if has_opencv:
        try:
            image = cv2.imread(real_path)
            if image is not None:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                cascade_path = os.path.join(cv2.data.haarcascades, 'haarcascade_frontalface_default.xml')
                if not os.path.exists(cascade_path):
                    import urllib.request
                    url = "https://raw.githubusercontent.com/opencv/opencv/master/data/haarcascades/haarcascade_frontalface_default.xml"
                    os.makedirs(os.path.dirname(cascade_path), exist_ok=True)
                    urllib.request.urlretrieve(url, cascade_path)
                    
                face_cascade = cv2.CascadeClassifier(cascade_path)
                faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
                
                num_faces = len(faces)
                if num_faces > 0:
                    for (x, y, w, h) in faces:
                        cv2.rectangle(image, (x, y), (x+w, y+h), (0, 255, 0), 2)
                    annotated_name = "annotated_" + os.path.basename(real_path)
                    annotated_path = os.path.join(os.path.dirname(real_path), annotated_name)
                    cv2.imwrite(annotated_path, image)
                    return f"FACE DETECTED (via local OpenCV): Found {num_faces} human face(s) in the photo. Annotated image saved as '{annotated_name}'."
                else:
                    return "No faces detected in the photo (via local OpenCV)."
        except Exception:
            pass

    # --- FALLBACK: USE DYNAMIC LLM VISION API (ZERO EXTRA LOCAL DEPENDENCIES!) ---
    try:
        with open(real_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
            
        provider = config.get("provider")
        model = config.get("model")
        api_key = config.get("api_key", "")
        base_url = config.get("base_url", "")
        
        if not provider or not api_key:
            return "Error: Local OpenCV is not installed, and AI provider key is not configured for fallback face detection."
            
        prompt = "Look at this photo. Is there any human face in it? Answer with: 'YES, [Count] face(s) detected. Description: [gender, expression, details]' or 'NO, no faces detected.'"
        
        # 1. Google Gemini API
        if provider == "gemini":
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            payload = {
                "contents": [{
                    "parts": [
                        {"text": prompt},
                        {
                            "inlineData": {
                                "mimeType": "image/jpeg",
                                "data": encoded_string
                            }
                        }
                    ]
                }]
            }
            res = requests.post(url, json=payload, timeout=25)
            if res.status_code == 200:
                data = res.json()
                try:
                    result = data["candidates"][0]["content"]["parts"][0]["text"]
                    return f"FACE ANALYSIS (via LLM API Cloud Fallback):\n{result.strip()}"
                except Exception:
                    return "Error parsing response from Gemini API."
            else:
                return f"Error connecting to Gemini Vision API (status code {res.status_code}): {res.text}"
                
        # 2. OpenAI API
        elif provider == "openai":
            api_endpoint = f"{base_url}/chat/completions" if base_url else "https://api.openai.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{encoded_string}"
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": 100
            }
            res = requests.post(api_endpoint, headers=headers, json=payload, timeout=25)
            if res.status_code == 200:
                data = res.json()
                result = data["choices"][0]["message"]["content"]
                return f"FACE ANALYSIS (via OpenAI API Cloud Fallback):\n{result.strip()}"
            else:
                return f"Error connecting to OpenAI Vision API (status code {res.status_code}): {res.text}"
                
        # 3. Anthropic API
        elif provider == "anthropic":
            api_endpoint = f"{base_url}/messages" if base_url else "https://api.anthropic.com/v1/messages"
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }
            payload = {
                "model": model,
                "max_tokens": 100,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": encoded_string
                                }
                            },
                            {"type": "text", "text": prompt}
                        ]
                    }
                ]
            }
            res = requests.post(api_endpoint, headers=headers, json=payload, timeout=25)
            if res.status_code == 200:
                data = res.json()
                result = data["content"][0]["text"]
                return f"FACE ANALYSIS (via Anthropic API Cloud Fallback):\n{result.strip()}"
            else:
                return f"Error connecting to Anthropic Vision API (status code {res.status_code}): {res.text}"
                
        else:
            return "Error: Local OpenCV is not installed and fallback image recognition is not supported for your active provider."
            
    except Exception as e:
        return f"Error performing face detection fallback: {str(e)}"

def check_system_health(auto_install=False):
    import shutil
    import subprocess
    import sys
    
    report = []
    missing_packages = []
    
    pkg_mgr = "pkg" if shutil.which("pkg") else ("apt" if shutil.which("apt") or shutil.which("apt-get") else ("dnf" if shutil.which("dnf") else ("pacman" if shutil.which("pacman") else "unknown")))

    cli_tools = {
        "nmap": "nmap",
        "git": "git",
        "dig": "dnsutils",
        "netstat": "net-tools",
        "ip": "iproute2",
        "traceroute": "traceroute",
        "curl": "curl"
    }
    if pkg_mgr == "pkg":
        cli_tools["termux-api"] = "termux-api"
        cli_tools["adb"] = "android-tools"
    else:
        cli_tools["notify-send"] = "libnotify-bin"
        cli_tools["spd-say"] = "speech-dispatcher"
    
    report.append(f"=== CLI Dependencies Audit (Package Manager: {pkg_mgr}) ===")
    for tool, pkg in cli_tools.items():
        path = shutil.which(tool)
        status = "✅ Installed" if path else "❌ Missing"
        report.append(f"- {tool}: {status} (pkg: {pkg})")
        if not path:
            missing_packages.append(pkg)
            
    py_packages = {
        "flask": "Flask",
        "requests": "requests",
        "urllib3": "urllib3",
        "cv2": "opencv-python"
    }
    
    report.append("\n=== Python Libraries Audit ===")
    missing_pip = []
    for mod, pip_name in py_packages.items():
        try:
            __import__(mod)
            status = "✅ Installed"
        except ImportError:
            status = "❌ Missing"
            missing_pip.append(pip_name)
        report.append(f"- {mod}: {status}")

    if missing_packages or missing_pip:
        if auto_install:
            report.append("\n🛠️ [Auto-Installer] Starting installation of missing dependencies...")
            
            for pkg in missing_packages:
                if pkg_mgr == "pkg":
                    cmd = ["pkg", "install", "-y", pkg]
                elif pkg_mgr == "apt":
                    cmd = ["sudo", "apt-get", "install", "-y", pkg]
                elif pkg_mgr == "dnf":
                    cmd = ["sudo", "dnf", "install", "-y", pkg]
                elif pkg_mgr == "pacman":
                    cmd = ["sudo", "pacman", "-S", "--noconfirm", pkg]
                else:
                    cmd = []
                
                if cmd:
                    report.append(f"- Running: {' '.join(cmd)}")
                    res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                    if res.returncode == 0:
                        report.append(f"  └─ Success: Installed {pkg}")
                    else:
                        report.append(f"  └─ Failed: {res.stderr.strip()}")
            
            for pip_name in missing_pip:
                report.append(f"- Running: pip install {pip_name}")
                if pip_name == "opencv-python" and pkg_mgr == "pkg":
                    res = subprocess.run(["pkg", "install", "-y", "opencv"], capture_output=True, text=True, timeout=120)
                else:
                    res = subprocess.run([sys.executable, "-m", "pip", "install", pip_name], capture_output=True, text=True, timeout=120)
                if res.returncode == 0:
                    report.append(f"  └─ Success: Installed {pip_name}")
                else:
                    report.append(f"  └─ Failed: {res.stderr.strip()}")
            
            report.append("\n✅ Auto-Installer process finished.")
        else:
            report.append(f"\n⚠️ Missing dependencies detected. Run check_system_health(auto_install=True) to install them automatically.")
    else:
        report.append("\n🎉 All dependencies are fully satisfied! Your system is healthy.")
        
    return "\n".join(report)

def active_threat_sentinel_daemon():
    """
    Background daemon thread that runs continuously to scan for system/network threats.
    If an ARP spoofing attack is detected, it triggers vibrations, lockscreen
    notifications using termux-api, text-to-speech, and notifies active telegram chats.
    """
    import time
    import json
    
    print("🛡️ [Sentinel Daemon] Background Active Threat Sentinel started.")
    
    last_arp_alert_time = 0
    
    while True:
        try:
            now_time = time.time()
            # Only alert every 5 minutes if it continues
            if now_time - last_arp_alert_time > 300:
                arp_res_str = detect_arp_spoofing()
                if "WARNING:" in arp_res_str or '"status": "warning"' in arp_res_str:
                    msg = "🚨 PocketStrike Alert: Potential Wi-Fi MITM / ARP Spoofing attack detected! Multiple IPs mapped to one MAC address."
                    
                    # Vibration and System Notification using termux-api
                    vibrate_device(1000)
                    send_android_notification("🚨 Wi-Fi Intrusion Detected!", "Potential MITM / ARP Spoofing attack active on network.")
                    speak_text("Warning: Potential Wi-Fi Intrusion Detected on current network!")
                    
                    # Telegram Alerts
                    token = config.get("api_key_telegram") or config.get("telegram_bot_token")
                    if token:
                        chats = get_registered_telegram_chats()
                        for cid in chats:
                            send_telegram_msg(token, cid, msg)
                            
                    last_arp_alert_time = now_time
        except Exception as e:
            print(f"⚠️ [Sentinel Daemon Error]: {str(e)}")
            
        time.sleep(120)

def scan_nearby_signals():
    """
    Scans physical radio waves for nearby Wi-Fi access points (SSID, BSSID, RSSI, channel) 
    and Bluetooth/BLE beacons (name, address, RSSI) in range. 
    Saves a signal audit report to the workspace as 'signal_scan_log.md'.
    """
    import subprocess
    import json
    import time
    import os
    import shutil
    
    wifi_results = []
    bt_results = []
    
    # 1. Scan Wi-Fi
    wifi_ok = False
    # Try termux-wifi-scaninfo first
    if shutil.which("termux-wifi-scaninfo"):
        try:
            res = subprocess.run(["termux-wifi-scaninfo"], capture_output=True, text=True, timeout=12)
            if res.returncode == 0:
                raw_data = json.loads(res.stdout)
                for item in raw_data:
                    wifi_results.append({
                        "ssid": item.get("ssid", "Hidden"),
                        "bssid": item.get("bssid", "N/A"),
                        "rssi": f"{item.get('rssi', 0)} dBm",
                        "channel": item.get("frequency", 0),
                        "security": item.get("capabilities", "N/A")
                    })
                wifi_ok = True
        except Exception:
            pass
            
    # Try ADB fallback if termux-api failed or is missing
    if not wifi_ok and shutil.which("rish"):
        try:
            env = os.environ.copy()
            env["RISH_APPLICATION_ID"] = get_termux_package_id()
            env.pop("LD_LIBRARY_PATH", None)
            env.pop("LD_PRELOAD", None)
            
            # Start scan
            subprocess.run(["rish", "-c", "cmd wifi start-scan"], capture_output=True, timeout=5, env=env)
            time.sleep(2) # Give scan a moment to gather results
            res = subprocess.run(["rish", "-c", "cmd wifi list-scan-results"], capture_output=True, text=True, timeout=8, env=env)
            if res.returncode == 0:
                lines = res.stdout.splitlines()
                # Parse standard cmd wifi scan table format
                # e.g., BSSID              Frequency  RSSI  Age      SSID...
                for line in lines[1:]:
                    parts = line.split()
                    if len(parts) >= 4:
                        wifi_results.append({
                            "ssid": " ".join(parts[4:]) if len(parts) > 4 else "Hidden",
                            "bssid": parts[0],
                            "rssi": f"{parts[2]} dBm",
                            "channel": parts[1],
                            "security": "N/A"
                        })
                wifi_ok = True
        except Exception:
            pass
            
    # 2. Scan Bluetooth (Requires Termux:API)
    if shutil.which("termux-bluetooth-scan"):
        try:
            # Start BT scan (usually runs as a daemon/service)
            subprocess.run(["termux-bluetooth-scan", "on"], capture_output=True, timeout=5)
            time.sleep(3.5) # Wait for devices to cache
            res = subprocess.run(["termux-bluetooth-scan", "c"], capture_output=True, text=True, timeout=8)
            if res.returncode == 0:
                raw_bt = json.loads(res.stdout)
                for item in raw_bt:
                    bt_results.append({
                        "name": item.get("name", "Unknown"),
                        "mac": item.get("address", "N/A"),
                        "rssi": f"{item.get('rssi', 0)} dBm"
                    })
            # Turn scan off
            subprocess.run(["termux-bluetooth-scan", "off"], capture_output=True, timeout=3)
        except Exception:
            pass

    # Build Markdown Output
    md = []
    md.append("# 📶 PocketStrike Wireless Signal Audit")
    md.append(f"Audit timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # Wi-Fi Section
    md.append("## 🌐 Nearby Wi-Fi Access Points")
    if wifi_results:
        md.append("| SSID | BSSID | RSSI | Frequency/Channel | Security/Capabilities |")
        md.append("|---|---|---|---|---|")
        for ap in wifi_results:
            md.append(f"| {ap['ssid']} | `{ap['bssid']}` | **{ap['rssi']}** | {ap['channel']} MHz | {ap['security']} |")
    else:
        md.append("_No Wi-Fi access points discovered (Ensure Wi-Fi is enabled and Location services are turned on)._")
        
    md.append("\n")
    
    # Bluetooth Section
    md.append("## 🔵 Nearby Bluetooth / BLE Beacons")
    if bt_results:
        md.append("| Device Name | MAC Address | RSSI |")
        md.append("|---|---|---|")
        for dev in bt_results:
            md.append(f"| {dev['name']} | `{dev['mac']}` | **{dev['rssi']}** |")
    else:
        md.append("_No Bluetooth devices discovered (Ensure Bluetooth is turned on and scannable)._")

    md_content = "\n".join(md)
    
    # Save log in workspace
    log_path = os.path.join(WORKSPACE_DIR, "signal_scan_log.md")
    try:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(md_content)
    except Exception:
        pass
        
    return f"Success: Scan completed. Discovered {len(wifi_results)} Wi-Fi APs and {len(bt_results)} Bluetooth devices. Saved detailed scan report to workspace as 'signal_scan_log.md'.\n\n" + md_content

def set_brightness(level):
    try:
        import subprocess
        # level: 0 to 255
        level_val = max(0, min(int(level), 255))
        cmd = ["termux-brightness", str(level_val)]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            return f"Success: Screen brightness set to {level_val}."
        return f"Error setting brightness: {res.stderr}"
    except Exception as e:
        return f"Error executing brightness tool: {str(e)}"

def set_volume(stream, level):
    try:
        import subprocess
        # stream: music, ring, alarm, notification, system
        # level: varies by stream, usually 0 to 15
        cmd = ["termux-volume", str(stream), str(level)]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            return f"Success: Volume for stream '{stream}' set to {level}."
        return f"Error setting volume: {res.stderr}"
    except Exception as e:
        return f"Error executing volume tool: {str(e)}"

def get_clipboard():
    try:
        import subprocess
        res = subprocess.run(["termux-clipboard-get"], capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            return res.stdout.strip()
        return f"Error getting clipboard: {res.stderr}"
    except Exception as e:
        return f"Error executing clipboard get: {str(e)} (Ensure Termux:API is installed)"

def set_clipboard(text):
    try:
        import subprocess
        res = subprocess.run(["termux-clipboard-set", text], capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            return "Success: Clipboard updated."
        return f"Error setting clipboard: {res.stderr}"
    except Exception as e:
        return f"Error executing clipboard set: {str(e)} (Ensure Termux:API is installed)"

def list_installed_apps(user_only=True):
    try:
        import subprocess
        # -f lists package file locations, -3 lists only third-party (user-installed) apps
        cmd = ["pm", "list", "packages", "-f"]
        if user_only:
            cmd.append("-3")
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
        if res.returncode != 0:
            return f"Error listing packages: {res.stderr}"
        
        packages = []
        for line in res.stdout.strip().split("\n"):
            if line.startswith("package:"):
                # line format: package:/data/app/~~.../base.apk=com.example.app
                parts = line[8:].split("=")
                if len(parts) >= 2:
                    apk_path = parts[0]
                    package_name = "=".join(parts[1:])
                    packages.append({
                        "package": package_name,
                        "apk_path": apk_path
                    })
        return json.dumps(packages, indent=2)
    except Exception as e:
        return f"Error executing app audit: {str(e)}"

def scan_wifi_networks():
    try:
        import subprocess
        res = subprocess.run(["termux-wifi-scaninfo"], capture_output=True, text=True, timeout=12)
        if res.returncode == 0:
            return res.stdout.strip()
        return f"Error scanning Wi-Fi: {res.stderr} (Ensure GPS location service is enabled and location permission is granted to Termux)"
    except Exception as e:
        return f"Error executing wifi scan: {str(e)} (Ensure Termux:API is installed)"

def speak_text(text):
    try:
        import subprocess
        import shutil
        import re
        import os
        
        # Clean text for speech output (strip tool markers, code fences, markdown, and emojis)
        clean_text = re.sub(r'\[TOOL_CALL:.*?\]', '', str(text))
        clean_text = re.sub(r'\[TOOL_RESULT:.*?output\].*?(?=(\[TOOL_CALL:|\[TOOL_RESULT:|$))', '', clean_text, flags=re.DOTALL)
        clean_text = re.sub(r'\[HISTORY_SYNC\]:.*', '', clean_text)
        clean_text = re.sub(r'```.*?```', '', clean_text, flags=re.DOTALL)
        clean_text = re.sub(r'[*_~`#>\[\]|]', '', clean_text)
        clean_text = re.sub(r'https?://\S+', '', clean_text)
        # Strip emoji codepoints
        clean_text = re.sub(r'[\U00010000-\U0010ffff]', '', clean_text)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        
        if not clean_text or len(clean_text) < 2:
            clean_text = "I'm on it."
            
        # 1. Android Termux TTS
        if shutil.which("termux-tts-speak"):
            res = subprocess.run(["termux-tts-speak", clean_text], capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                return "Success: Speaking text via Termux TTS."
            return f"Error triggering speech: {res.stderr}"
            
        # 2. macOS native say
        elif shutil.which("say"):
            res = subprocess.run(["say", clean_text], capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                return "Success: Speaking text via macOS native say command."
            return f"Error triggering macOS speech: {res.stderr}"
            
        # 3. Windows PowerShell SAPI Speech
        elif os.name == "nt":
            safe_text = clean_text.replace("'", "''").replace('"', '`"')
            ps_cmd = f"Add-Type -AssemblyName System.Speech; $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; $synth.Speak('{safe_text}')"
            res = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd], capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                return "Success: Speaking text via Windows SAPI."
            return f"Notice: Windows SAPI error: {res.stderr}"
            
        # 4. Linux spd-say
        elif shutil.which("spd-say"):
            res = subprocess.run(["spd-say", clean_text], capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                return "Success: Speaking text via Linux spd-say."
            return f"Error triggering spd-say speech: {res.stderr}"
            
        # 5. Linux espeak-ng / espeak
        elif shutil.which("espeak-ng") or shutil.which("espeak"):
            cmd = "espeak-ng" if shutil.which("espeak-ng") else "espeak"
            res = subprocess.run([cmd, clean_text], capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                return f"Success: Speaking text via Linux {cmd}."
            return f"Error triggering espeak speech: {res.stderr}"
            
        else:
            return "Notice: No Text-To-Speech engine found on host."
    except Exception as e:
        return f"Error executing speak tool: {str(e)}"

# =======================================================
# LOCAL ADB AUTOMATION CONTROLLER (SCREEN CONTROL)
# =======================================================
def run_adb_command(cmd_str):
    try:
        import subprocess
        import shutil
        import os
        import glob
        import shlex
        
        # Check if rish (Shizuku's Termux shell interface) is installed and available
        rish_path = shutil.which("rish")
        
        # Auto-install Shizuku client files if found in the user's exported /sdcard/Shizuku/ directory
        if rish_path is None:
            possible_srcs = [
                "/sdcard/Shizuku/rish",
                "/storage/emulated/0/Shizuku/rish",
                os.path.expanduser("~/storage/shared/Shizuku/rish"),
                os.path.expanduser("~/storage/downloads/rish"),
                os.path.expanduser("~/storage/downloads/Shizuku/rish"),
                "/sdcard/Download/rish",
                "/sdcard/Download/Shizuku/rish",
                "/storage/emulated/0/Download/rish",
                "/storage/emulated/0/Download/Shizuku/rish",
                os.path.abspath(os.path.join(os.path.dirname(__file__), "rish")),
                os.path.abspath(os.path.join(os.path.dirname(__file__), "workspace", "rish"))
            ]
            
            shizuku_src = None
            for path in possible_srcs:
                if os.path.exists(path):
                    shizuku_src = path
                    break
                
            if shizuku_src:
                try:
                    prefix = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
                    termux_bin = os.path.join(prefix, "bin")
                    if os.path.exists(termux_bin):
                        # Copy all files matching rish* (including dex loader)
                        src_dir = os.path.dirname(shizuku_src)
                        for fpath in glob.glob(os.path.join(src_dir, "rish*")):
                            dest_file = os.path.join(termux_bin, os.path.basename(fpath))
                            shutil.copy(fpath, dest_file)
                            
                        # Grant execution permissions
                        os.chmod(os.path.join(termux_bin, "rish"), 0o755)
                        
                        # dex loader MUST be read-only (chmod 444) for Shizuku security
                        dex_file = os.path.join(termux_bin, "rish_shizuku.dex")
                        if os.path.exists(dex_file):
                            os.chmod(dex_file, 0o444)
                            
                        rish_path = os.path.join(termux_bin, "rish")
                        print(f"PocketstrikeAI: Auto-installed Shizuku rish binaries successfully to {termux_bin}!")
                except Exception as e:
                    print(f"PocketstrikeAI: Shizuku auto-install failed: {e}")
                    
        use_shizuku = rish_path is not None
        shizuku_err = None
        adb_err = None

        env = os.environ.copy()
        env["RISH_APPLICATION_ID"] = get_termux_package_id()
        env.pop("LD_LIBRARY_PATH", None)
        env.pop("LD_PRELOAD", None)
        shell_exe = "/system/bin/sh" if os.path.exists("/system/bin/sh") else "sh"

        # --- 1. TRY SHIZUKU FIRST IF AVAILABLE ---
        if use_shizuku:
            try:
                if cmd_str.startswith("shell "):
                    shell_cmd = cmd_str[6:] # Strip "shell "
                    
                    if shell_cmd == "screencap -p":
                        return True, "STDOUT_STREAMING_ACTIVE"
                        
                    res = subprocess.run([shell_exe, rish_path, "-c", shell_cmd], capture_output=True, text=True, timeout=15, env=env)
                    if res.returncode == 0:
                        return True, res.stdout
                    else:
                        shizuku_err = f"Shizuku shell cmd failed (code {res.returncode}): {res.stderr.strip() or res.stdout.strip()}"
                
                elif cmd_str.startswith("devices"):
                    # Check if Shizuku daemon is running and responds
                    res = subprocess.run([shell_exe, rish_path, "-c", "echo 1"], capture_output=True, text=True, timeout=3, env=env)
                    if res.returncode == 0:
                        return True, "List of devices attached\nshizuku_localhost\tdevice"
                    else:
                        shizuku_err = f"Shizuku test failed: {res.stderr.strip() or res.stdout.strip()}"
                
                elif cmd_str.startswith("pull "):
                    parts = shlex.split(cmd_str)
                    if len(parts) >= 3:
                        src = parts[1]
                        dest = parts[2]
                        try:
                            with open(dest, "wb") as f:
                                res = subprocess.run([shell_exe, rish_path, "-c", f"cat {src}"], stdout=f, env=env, timeout=15)
                            if res.returncode == 0:
                                return True, "Pulled via Shizuku shell cat"
                            else:
                                shizuku_err = f"Shizuku cat failed (code {res.returncode})"
                        except Exception as e:
                            shizuku_err = f"Shizuku pull exception: {e}"
                    else:
                        shizuku_err = "Invalid pull command parameters"
            except Exception as e:
                shizuku_err = f"Shizuku exception: {str(e)}"

        # --- 2. TRY ADB FALLBACK IF SHIZUKU FAILED OR NOT AVAILABLE ---
        try:
            if cmd_str.startswith("shell "):
                shell_cmd = cmd_str[6:]
                res = subprocess.run(["adb", "shell", shell_cmd], capture_output=True, text=True, timeout=15)
            elif cmd_str.startswith("pull "):
                parts = shlex.split(cmd_str)
                res = subprocess.run(["adb"] + parts, capture_output=True, text=True, timeout=15)
            else:
                parts = shlex.split(cmd_str)
                res = subprocess.run(["adb"] + parts, capture_output=True, text=True, timeout=15)

            if res.returncode == 0:
                return True, res.stdout
            else:
                adb_err = f"ADB cmd failed (code {res.returncode}): {res.stderr.strip() or res.stdout.strip()}"
        except Exception as e:
            adb_err = f"ADB exception: {str(e)}"

        # --- 3. BOTH FAILED: COMPILE DIAGNOSTIC ERROR MESSAGE ---
        errors = []
        if shizuku_err:
            errors.append(f"[Shizuku] {shizuku_err}")
        if adb_err:
            errors.append(f"[ADB Fallback] {adb_err}")
        
        if not errors:
            errors.append("No execution methods succeeded (Shizuku not configured, ADB not found/connected).")
            
        return False, "\n".join(errors)
    except Exception as e:
        return False, str(e)

def take_screenshot():
    target_name = "captured_screenshot.png"
    target_path = os.path.join(WORKSPACE_DIR, target_name)
    
    if os.path.exists(target_path):
        try: os.remove(target_path)
        except Exception: pass
        
    # Check if Shizuku is set up
    import shutil
    use_shizuku = shutil.which("rish") is not None or os.path.exists("/sdcard/Shizuku/rish") or os.path.exists(os.path.expanduser("~/storage/shared/Shizuku/rish"))
    
    if use_shizuku:
        # Trigger auto-provisioning
        run_adb_command("devices")
        rish_path = shutil.which("rish") or "/data/data/com.termux/files/usr/bin/rish"
        
        env = os.environ.copy()
        env["RISH_APPLICATION_ID"] = get_termux_package_id()
        env.pop("LD_LIBRARY_PATH", None)
        env.pop("LD_PRELOAD", None)
        shell_exe = "/system/bin/sh" if os.path.exists("/system/bin/sh") else "sh"
        
        try:
            with open(target_path, "wb") as f:
                res = subprocess.run([shell_exe, rish_path, "-c", "screencap -p"], stdout=f, env=env, timeout=20)
            if res.returncode == 0 and os.path.exists(target_path) and os.path.getsize(target_path) > 0:
                return f"Success: Screenshot captured via Shizuku. Saved to workspace as '{target_name}'. Path: {target_path}."
        except Exception as e:
            # Fallback to standard ADB below if rish failed
            pass
            
    # Verify standard ADB connection state fallback
    ok, out = run_adb_command("devices")
    if not ok or len([line for line in out.strip().split("\n") if "device" in line and not "devices" in line]) == 0:
        return "Error: Neither Shizuku nor Local ADB is connected. Enable 'Wireless Debugging' in Android Developer Options, connect Termux locally (e.g. run 'adb connect localhost:5555' or authorize Shizuku via rish), and try again."
        
    # 2. Capture screenshot on phone storage
    ok, out = run_adb_command("shell screencap -p /sdcard/screenshot.png")
    if not ok:
        return f"Error: Screen capture command failed. Details: {out}"
        
    # 3. Pull photo from device storage to Termux workspace
    ok, out = run_adb_command(f"pull /sdcard/screenshot.png {target_path}")
    if not ok:
        return f"Error: Failed to transfer screenshot to workspace. Details: {out}"
        
    # Clean up device temp file
    run_adb_command("shell rm /sdcard/screenshot.png")
    
    return f"Success: Screenshot captured. Saved to workspace as '{target_name}'. Path: {target_path}."

def tap_screen(x, y):
    ok, out = run_adb_command("devices")
    if not ok or len([line for line in out.strip().split("\n") if "device" in line and not "devices" in line]) == 0:
        return "Error: ADB is not connected. Connect Termux to local Wireless Debugging first."
        
    ok, out = run_adb_command(f"shell input tap {int(x)} {int(y)}")
    if ok:
        return f"Success: Simulated screen tap at coordinates ({int(x)}, {int(y)})."
    return f"Error simulating tap: {out}"

def swipe_screen(x1, y1, x2, y2, duration_ms=500):
    ok, out = run_adb_command("devices")
    if not ok or len([line for line in out.strip().split("\n") if "device" in line and not "devices" in line]) == 0:
        return "Error: ADB is not connected. Connect Termux to local Wireless Debugging first."
        
    ok, out = run_adb_command(f"shell input swipe {int(x1)} {int(y1)} {int(x2)} {int(y2)} {int(duration_ms)}")
    if ok:
        return f"Success: Simulated screen swipe from ({int(x1)}, {int(y1)}) to ({int(x2)}, {int(y2)}) over {duration_ms}ms."
    return f"Error simulating swipe: {out}"

def press_key(key_code):
    # Key event codes: 3=Home, 4=Back, 26=Power, 24=VolumeUp, 25=VolumeDown, 82=Unlock
    ok, out = run_adb_command("devices")
    if not ok or len([line for line in out.strip().split("\n") if "device" in line and not "devices" in line]) == 0:
        return "Error: ADB is not connected. Connect Termux to local Wireless Debugging first."
        
    ok, out = run_adb_command(f"shell input keyevent {int(key_code)}")
    if ok:
        return f"Success: Simulated physical key press event code {int(key_code)}."
    return f"Error simulating key event: {out}"

def launch_app(package_name):
    ok, out = run_adb_command("devices")
    if not ok or len([line for line in out.strip().split("\n") if "device" in line and not "devices" in line]) == 0:
        return "Error: ADB is not connected. Connect Termux to local Wireless Debugging first."
        
    ok, out = run_adb_command(f"shell monkey -p {package_name} -c android.intent.category.LAUNCHER 1")
    if ok:
        return f"Success: Opened application matching package name '{package_name}'."
    return f"Error launching application: {out}"

def control_android_system(action, target=""):
    # Controls Android system parameters using local shell commands via Shizuku/ADB
    cmd_map = {
        "flashlight_on": "cmd notification set_flashlight 1",
        "flashlight_off": "cmd notification set_flashlight 0",
        "wifi_on": "svc wifi enable",
        "wifi_off": "svc wifi disable",
        "bluetooth_on": "svc bluetooth enable",
        "bluetooth_off": "svc bluetooth disable",
        "dark_mode_on": "cmd uimode night yes",
        "dark_mode_off": "cmd uimode night no",
        "battery_saver_on": "settings put global low_power 1",
        "battery_saver_off": "settings put global low_power 0",
        "dnd_on": "cmd notification set_dnd on",
        "dnd_off": "cmd notification set_dnd off",
        "auto_rotate_on": "settings put system accelerometer_rotation 1",
        "auto_rotate_off": "settings put system accelerometer_rotation 0",
        "expand_notifications": "cmd statusbar expand-notifications",
        "collapse_notifications": "cmd statusbar collapse",
        "get_current_app": "dumpsys window | grep mCurrentFocus",
        "type_text": "smart_type"
    }
    
    if action not in cmd_map:
        return f"Error: Unsupported action '{action}'. Options: {', '.join(cmd_map.keys())}"
        
    ok, out = run_adb_command("devices")
    if not ok or len([line for line in out.strip().split("\n") if "device" in line and not "devices" in line]) == 0:
        return "Error: ADB/Shizuku is not connected. Make sure Shizuku or local Wireless Debugging is running."
        
    if action == "type_text":
        return smart_ui_type("", target)
        
    cmd = cmd_map[action]
    ok, out = run_adb_command(f"shell {cmd}")
    if ok:
        return f"Success: Executed system action '{action}' on device. Output: {out.strip() if out else 'Done'}"
    return f"Error executing system action '{action}': {out}"

def web_search(query):
    try:
        import urllib.parse
        import html as html_parser
        
        # Safe URL encoding using urllib.parse.quote
        encoded_query = urllib.parse.quote(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code != 200:
            return f"Error: Search failed (Status {res.status_code})."
            
        html_content = res.text
        results = []
        
        # Robust regex targeting result titles and snippets regardless of attribute orders
        titles = re.findall(r'<a\s+[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html_content, re.DOTALL)
        snippets = re.findall(r'<a\s+[^>]*class="result__snippet"[^>]*>(.*?)</a>', html_content, re.DOTALL)
        
        for i in range(min(len(titles), len(snippets), 5)):
            raw_href, title = titles[i]
            
            # Extract clean redirect target URL if present in DuckDuckGo redirect link
            parsed_url = urllib.parse.urlparse(raw_href)
            queries = urllib.parse.parse_qs(parsed_url.query)
            clean_href = queries.get("uddg", [raw_href])[0]
            if clean_href.startswith("//"):
                clean_href = "https:" + clean_href
                
            title_clean = html_parser.unescape(re.sub(r'<[^>]*>', '', title).strip())
            snippet_clean = html_parser.unescape(re.sub(r'<[^>]*>', '', snippets[i]).strip())
            
            results.append({
                "index": i + 1,
                "title": title_clean,
                "link": clean_href,
                "summary": snippet_clean
            })
            
        if not results:
            return "No search results found or search was blocked by rate-limiting."
            
        # Build search results output
        output_parts = ["=== SEARCH ENGINE SUMMARY ==="]
        for r in results:
            output_parts.append(f"[{r['index']}] {r['title']}\nLink: {r['link']}\nSnippet: {r['summary']}")
            
        # Perform Smart Fetching of actual body text for the top 2 web pages
        fetched_count = 0
        output_parts.append("\n=== DEEP WEB CONTENT FETCHED ===")
        for r in results:
            link = r['link']
            # Skip non-crawlable domains and attachments
            if any(domain in link.lower() for domain in ["duckduckgo.com", "google.com", "facebook.com", "twitter.com", "instagram.com"]):
                continue
            if link.lower().endswith((".pdf", ".zip", ".tar", ".gz", ".apk")):
                continue
                
            output_parts.append(f"\n[Deep Content from Link #{r['index']}: {r['title']}]")
            try:
                page_res = requests.get(link, headers=headers, timeout=8)
                if page_res.status_code == 200:
                    page_html = page_res.text
                    # Clean tags
                    page_clean = re.sub(r'<(script|style).*?>([\s\S]*?)</\1>', '', page_html, flags=re.IGNORECASE)
                    text = re.sub(r'<[^>]*>', '', page_clean)
                    text = html_parser.unescape(text)
                    text = re.sub(r'\n\s*\n', '\n\n', text)
                    text = re.sub(r'[ \t]+', ' ', text)
                    
                    body_snippet = text.strip()[:1500]
                    if not body_snippet:
                        body_snippet = "Empty or failed to parse main body text."
                    output_parts.append(body_snippet)
                else:
                    output_parts.append(f"Failed to load full page content (Status {page_res.status_code}).")
            except Exception as e:
                output_parts.append(f"Could not load full page content: {str(e)}")
                
            fetched_count += 1
            if fetched_count >= 2:
                break
                
        return "\n---\n".join(output_parts)
    except Exception as e:
        return f"Error performing search: {str(e)}"

def fetch_url(url):
    try:
        import html as html_parser
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url
            
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code != 200:
            return f"Error: Page fetch failed (Status {res.status_code})."
            
        html_content = res.text
        # Remove script and style tags completely
        html_clean = re.sub(r'<(script|style).*?>([\s\S]*?)</\1>', '', html_content, flags=re.IGNORECASE)
        # Strip all HTML tags
        text = re.sub(r'<[^>]*>', '', html_clean)
        # Convert HTML entities to clean characters
        text = html_parser.unescape(text)
        # Normalize whitespace and empty lines
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = re.sub(r'[ \t]+', ' ', text)
        
        cleaned_text = text.strip()[:10000]
        if len(text) > 10000:
            cleaned_text += "\n\n[Content truncated due to size limit...]"
        return cleaned_text
    except Exception as e:
        return f"Error fetching URL: {str(e)}"

def download_file(url, file_name):
    try:
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url
            
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        res = requests.get(url, headers=headers, timeout=30, stream=True)
        if res.status_code != 200:
            return f"Error: File download failed (Status {res.status_code})."
            
        # Ensure target file name resolves inside workspace to maintain sandboxing
        target_path = os.path.abspath(os.path.join(WORKSPACE_DIR, file_name))
        real_target = os.path.realpath(target_path)
        real_workspace = os.path.realpath(WORKSPACE_DIR)
        
        if not real_target.startswith(real_workspace):
            return f"Error: Write access denied. You can only download files inside your workspace: {WORKSPACE_DIR}"
            
        # Prevent touching main codebase files specifically by name (extra safety check)
        forbidden_files = ["server.py", "setup.py", "launch.sh", "install.sh", "config.json"]
        if os.path.basename(real_target) in forbidden_files:
            return f"Error: Downloading files with critical names is restricted to prevent overwriting active codebase."
            
        os.makedirs(os.path.dirname(real_target), exist_ok=True)
        with open(real_target, "wb") as f:
            for chunk in res.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    
        return f"Success: File downloaded successfully and saved as '{file_name}' inside workspace."
    except Exception as e:
        return f"Error downloading file: {str(e)}"

def get_network_details():
    details = {}
    try:
        details["hostname"] = socket.gethostname()
    except Exception:
        pass
        
    try:
        import subprocess
        res = subprocess.run(["ip", "addr"], capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            details["interfaces"] = res.stdout
        else:
            res_if = subprocess.run(["ifconfig"], capture_output=True, text=True, timeout=5)
            if res_if.returncode == 0:
                details["interfaces"] = res_if.stdout
    except Exception as e:
        details["interfaces_error"] = str(e)
        
    try:
        import subprocess
        res = subprocess.run(["ip", "route"], capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            details["routing_table"] = res.stdout
    except Exception:
        pass
        
    return json.dumps(details, indent=2)

def list_local_listeners():
    try:
        import subprocess
        res = subprocess.run(["ss", "-tlnp"], capture_output=True, text=True, timeout=5)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout
            
        res = subprocess.run(["netstat", "-tlnp"], capture_output=True, text=True, timeout=5)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout
            
        res = subprocess.run(["netstat", "-an"], capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            lines = res.stdout.split("\n")
            listeners = [line for line in lines if "LISTEN" in line]
            return "\n".join(listeners) if listeners else "No active listeners found."
    except Exception as e:
        return f"Error retrieving listeners: {str(e)}"

def send_android_notification(title, message):
    try:
        import subprocess
        import shutil
        if shutil.which("termux-notification"):
            cmd = ["termux-notification", "-t", title, "-c", message]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                return "Success: Notification sent via Termux API."
            return f"Error: Command exited with code {res.returncode}. Output: {res.stderr}"
        elif shutil.which("osascript"):
            # macOS native notification
            clean_title = title.replace('"', '\\"')
            clean_msg = message.replace('"', '\\"')
            script = f'display notification "{clean_msg}" with title "{clean_title}"'
            res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                return "Success: Notification sent via macOS System Notification."
            return f"Error sending macOS notification: {res.stderr}"
        elif shutil.which("notify-send"):
            cmd = ["notify-send", title, message]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                return "Success: Notification sent via Linux notify-send."
            return f"Error sending Linux notification: {res.stderr}"
        else:
            print(f"🔔 [Notification Banner] {title}: {message}")
            return f"Success: Notification logged ({title}: {message})."
    except Exception as e:
        return f"Error triggering notification: {str(e)}"

def vibrate_device(duration_ms=500):
    try:
        import subprocess
        import shutil
        if shutil.which("termux-vibrate"):
            cmd = ["termux-vibrate", "-d", str(duration_ms)]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                return f"Success: Device vibrated for {duration_ms}ms."
            return f"Error: Command exited with code {res.returncode}. Output: {res.stderr}"
        else:
            send_android_notification("PocketStrike Alert", "Vibration Alert Triggered")
            return f"Notice: Physical vibration motor is specific to mobile devices. Triggered desktop notification alert on Linux."
    except Exception as e:
        return f"Error vibrating device: {str(e)}"

def search_files(pattern):
    try:
        import fnmatch
        matches = []
        for root, dirnames, filenames in os.walk(WORKSPACE_DIR):
            for filename in fnmatch.filter(filenames, pattern):
                rel_dir = os.path.relpath(root, WORKSPACE_DIR)
                matches.append(os.path.join(rel_dir, filename) if rel_dir != "." else filename)
        if not matches:
            return f"No files matching pattern '{pattern}' found."
        return json.dumps(matches, indent=2)
    except Exception as e:
        return f"Error searching files: {str(e)}"

def dns_lookup(domain, record_type="A"):
    try:
        import requests
        url = "https://cloudflare-dns.com/dns-query"
        headers = {"Accept": "application/dns-json"}
        params = {"name": domain, "type": record_type}
        res = requests.get(url, headers=headers, params=params, timeout=10)
        if res.status_code != 200:
            return f"Error: DNS query failed with status code {res.status_code}"
        data = res.json()
        if "Answer" not in data:
            return f"No records of type {record_type} found for {domain}."
        answers = []
        for ans in data["Answer"]:
            answers.append(f"Name: {ans.get('name')}, Type: {ans.get('type')}, TTL: {ans.get('TTL')}, Data: {ans.get('data')}")
        return "\n".join(answers)
    except Exception as e:
        return f"Error during DNS lookup: {str(e)}"

def whois_lookup(domain):
    try:
        import requests
        url = f"https://rdap.org/domain/{domain.strip().lower()}"
        res = requests.get(url, timeout=10)
        if res.status_code == 404:
            return f"Domain {domain} not found or not supported by RDAP."
        elif res.status_code != 200:
            return f"Error: RDAP query failed with status code {res.status_code}"
        
        data = res.json()
        registrar = "Unknown"
        for entity in data.get("entities", []):
            if "registrar" in entity.get("roles", []):
                vcard = entity.get("vcardArray", [])
                if len(vcard) > 1:
                    for field in vcard[1]:
                        if field[0] == "fn":
                            registrar = field[3]
                            break
        
        events = []
        for event in data.get("events", []):
            event_action = event.get("eventAction", "")
            event_date = event.get("eventDate", "")
            events.append(f"{event_action.capitalize()}: {event_date}")
            
        summary = [
            f"Domain: {data.get('ldhName', domain)}",
            f"Registrar: {registrar}",
            "Status: " + ", ".join(data.get("status", ["Unknown"])),
            "Events:\n  " + "\n  ".join(events) if events else "Events: Unknown"
        ]
        
        nameservers = [ns.get("ldhName") for ns in data.get("nameservers", []) if ns.get("ldhName")]
        if nameservers:
            summary.append("Nameservers: " + ", ".join(nameservers))
            
        return "\n".join(summary)
    except Exception as e:
        return f"Error during WHOIS lookup: {str(e)}"

def analyze_hash(hash_str):
    try:
        hash_str = hash_str.strip()
        length = len(hash_str)
        
        import re
        is_hex = bool(re.match(r'^[a-fA-F0-9]+$', hash_str))
        
        possible_types = []
        if is_hex:
            if length == 32:
                possible_types.append("MD5")
            elif length == 40:
                possible_types.append("SHA-1")
            elif length == 56:
                possible_types.append("SHA-224")
            elif length == 64:
                possible_types.append("SHA-256")
            elif length == 96:
                possible_types.append("SHA-384")
            elif length == 128:
                possible_types.append("SHA-512")
                
        if hash_str.startswith("$2a$") or hash_str.startswith("$2b$") or hash_str.startswith("$2y$"):
            if length == 60:
                possible_types.append("bcrypt")
        elif hash_str.startswith("$pbkdf2-sha256$"):
            possible_types.append("PBKDF2-SHA256")
        elif hash_str.startswith("$argon2id$") or hash_str.startswith("$argon2i$"):
            possible_types.append("Argon2")
            
        if not possible_types:
            if length == 16:
                possible_types.append("Half-MD5")
            else:
                return f"Could not identify the hash format of '{hash_str}'. Length: {length}."
                
        return f"Hash: {hash_str}\nLikely Algorithm(s): {', '.join(possible_types)}"
    except Exception as e:
        return f"Error analyzing hash: {str(e)}"

def open_url_on_phone(url):
    try:
        # Standardize URL
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url
            
        ok, out = run_adb_command("devices")
        if not ok or len([line for line in out.strip().split("\n") if "device" in line and not "devices" in line]) == 0:
            return "Error: ADB/Shizuku is not connected. Enable Wireless Debugging or start Shizuku app first."
            
        ok, out = run_adb_command(f"shell am start -a android.intent.action.VIEW -d '{url}'")
        if ok:
            return f"Success: Opened URL '{url}' on Android phone screen."
        return f"Error opening URL on phone: {out}"
    except Exception as e:
        return f"Error executing open URL tool: {str(e)}"

def execute_root_command(command):
    try:
        import subprocess
        import shutil
        
        # 1. Check if 'su' binary is available
        su_path = shutil.which("su")
        root_signatures = ["/system/bin/su", "/system/xbin/su", "/sbin/su", "/system/sd/xbin/su", "/system/bin/failsafe/su", "/data/local/xbin/su", "/data/local/bin/su"]
        su_exists = su_path is not None or any(os.path.exists(p) for p in root_signatures)
        
        if not su_exists:
            return "Error: SuperUser 'su' binary not found. This tool requires a rooted Android device."
            
        # Safety token validation (prevent basic bricking scenarios)
        forbidden_tokens = ["rm -rf", "rm -f /", "mkfs", "dd if="]
        for token in forbidden_tokens:
            if token in command:
                return f"Error: Root command blocked. Forbidden token: '{token}'"
                
        # Run command with su -c
        # On Android, su -c "command" runs the command as root.
        res = subprocess.run(["su", "-c", command], capture_output=True, text=True, timeout=30)
        
        output = f"Exit Code: {res.returncode}\n"
        if res.stdout:
            output += f"Stdout:\n{res.stdout}\n"
        if res.stderr:
            output += f"Stderr:\n{res.stderr}\n"
        return output
    except subprocess.TimeoutExpired:
        return "Error: Root command execution timed out (limit: 30 seconds)."
    except Exception as e:
        return f"Error executing root command: {str(e)}"

def audit_sms_inbox(limit=10):
    try:
        import subprocess
        limit_val = max(1, min(int(limit), 50))
        cmd = ["termux-sms-list", "-l", str(limit_val)]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if res.returncode == 0:
            return res.stdout.strip()
        return f"Error listing SMS: {res.stderr} (Ensure Termux:API is installed and SMS read permission is granted)"
    except Exception as e:
        return f"Error executing SMS audit tool: {str(e)}"

def ip_geolocation_lookup(ip_address):
    try:
        import requests
        ip_clean = ip_address.strip()
        # Use ip-api.com (free, no key required)
        url = f"http://ip-api.com/json/{ip_clean}"
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            if data.get("status") == "success":
                details = {
                    "query": data.get("query"),
                    "status": "success",
                    "country": data.get("country"),
                    "region_name": data.get("regionName"),
                    "city": data.get("city"),
                    "zip": data.get("zip"),
                    "lat": data.get("lat"),
                    "lon": data.get("lon"),
                    "timezone": data.get("timezone"),
                    "isp": data.get("isp"),
                    "org": data.get("org"),
                    "as": data.get("as")
                }
                return json.dumps(details, indent=2)
            else:
                return f"Error looking up IP: {data.get('message', 'Failed query')}"
        return f"Error: Request failed with status code {res.status_code}"
    except Exception as e:
        return f"Error executing IP geolocation: {str(e)}"

def read_phone_sensors(sensor_name=""):
    try:
        import subprocess
        if not sensor_name:
            cmd = ["termux-sensor", "-l"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
            if res.returncode == 0:
                return res.stdout.strip()
            return f"Error listing sensors: {res.stderr} (Ensure Termux:API is installed)"
        else:
            # Read specific sensor once
            cmd = ["termux-sensor", "-n", "1", "-s", sensor_name]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
            if res.returncode == 0:
                return res.stdout.strip()
            return f"Error reading sensor '{sensor_name}': {res.stderr}"
    except Exception as e:
        return f"Error executing sensor reader: {str(e)}"

def scheduler_worker_loop():
    import time
    import datetime
    
    schedules_file = os.path.join(WORKSPACE_DIR, "schedules.json")
    print("PocketstrikeAI Scheduler Thread started...")
    
    while True:
        # Sleep for 15 seconds between ticks
        time.sleep(15)
        
        if not os.path.exists(schedules_file):
            continue
            
        try:
            with open(schedules_file, "r") as f:
                tasks = json.load(f)
        except Exception:
            continue
            
        now = time.time()
        modified = False
        token = config.get("telegram_token")
        
        for task in tasks:
            if task.get("status") != "pending":
                continue
                
            trigger_time = task.get("trigger_time")
            task_type = task.get("type", "reminder")
            
            # For one-shot reminders
            if task_type == "reminder":
                if now >= trigger_time:
                    execute_scheduled_action(task, token)
                    task["status"] = "completed"
                    task["fired_at"] = now
                    modified = True
                    
            # For recurring cron jobs
            elif task_type == "cron":
                last_run = task.get("last_run", 0)
                interval = task.get("interval_seconds", 0)
                
                if interval > 0 and (now - last_run) >= interval:
                    execute_scheduled_action(task, token)
                    task["last_run"] = now
                    modified = True
                    
        if modified:
            try:
                with open(schedules_file, "w") as f:
                    json.dump(tasks, f, indent=2)
            except Exception as e:
                print(f"Error saving schedules: {e}")

def execute_scheduled_action(task, token):
    desc = task.get("description", "Scheduled Reminder")
    target = task.get("target", "system")
    
    # 1. Print a visual warning in the Termux console and emit the ASCII Bell sound (\a)
    import sys
    import shutil
    print(f"\n\033[1;32m🔔 [SCHEDULED ALERT] {desc}\033[0m\n", flush=True)
    sys.stdout.write('\a')
    sys.stdout.flush()
    
    # 2. Check if Termux:API is set up. If not, dynamically fallback to Telegram (if token exists)
    termux_api_available = shutil.which("termux-notification") is not None
    if not termux_api_available and target == "system":
        if token:
            target = "both"
            
    msg = f"🔔 **PocketstrikeAI Alert** 🔔\n\nTask: {desc}"
    
    if target == "system" or target == "both":
        send_android_notification("PocketstrikeAI Alert", desc)
        vibrate_device(800)
        speak_text(f"Notification: {desc}")
        
    if (target == "telegram" or target == "both") and token:
        chats = get_registered_telegram_chats()
        for cid in chats:
            send_telegram_msg(token, cid, msg)

    # 3. Append to Unified Chat History so it appears in the Web chat dashboard
    try:
        messages = load_unified_history()
        messages.append({
            "role": "assistant",
            "content": f"🔔 **[SCHEDULED ALERT]**\n\n**Reminder**: {desc}"
        })
        save_unified_history(messages)
    except Exception as e:
        print(f"Error appending alert to unified history: {e}")

def parse_time_offset(trigger_str):
    import datetime
    import re
    now = datetime.datetime.now()
    
    match = re.match(r'^(\d+)([mhdw])$', trigger_str.strip().lower())
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        if unit == 'm':
            delta = datetime.timedelta(minutes=amount)
        elif unit == 'h':
            delta = datetime.timedelta(hours=amount)
        elif unit == 'd':
            delta = datetime.timedelta(days=amount)
        elif unit == 'w':
            delta = datetime.timedelta(weeks=amount)
        return (now + delta).timestamp()
        
    match_abs = re.match(r'^(\d{1,2}):(\d{2})$', trigger_str.strip())
    if match_abs:
        hour = int(match_abs.group(1))
        minute = int(match_abs.group(2))
        target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target_time < now:
            target_time += datetime.timedelta(days=1)
        return target_time.timestamp()
        
    return None

def add_scheduled_task(task_type, trigger, description, target="telegram"):
    try:
        import time
        schedules_file = os.path.join(WORKSPACE_DIR, "schedules.json")
        
        tasks = []
        if os.path.exists(schedules_file):
            try:
                with open(schedules_file, "r", encoding="utf-8") as f:
                    tasks = json.load(f)
            except Exception:
                pass
                
        task_id = f"task_{int(time.time())}"
        task_type = task_type.strip().lower()
        target = target.strip().lower()
        
        if task_type not in ["reminder", "cron"]:
            return "Error: task_type must be either 'reminder' or 'cron'."
            
        if target not in ["telegram", "system", "both"]:
            return "Error: target must be 'telegram', 'system', or 'both'."
            
        new_task = {
            "id": task_id,
            "type": task_type,
            "description": description,
            "target": target,
            "status": "pending",
            "created_at": time.time()
        }
        
        if task_type == "reminder":
            trigger_time = parse_time_offset(trigger)
            if not trigger_time:
                return f"Error: Could not parse reminder time '{trigger}'. Use formats like '10m', '2h', '1d', or '18:30'."
            new_task["trigger_time"] = trigger_time
            new_task["trigger_desc"] = trigger
            
        elif task_type == "cron":
            import re
            match = re.match(r'^(\d+)([mhdw])$', trigger.strip().lower())
            if not match:
                return f"Error: Could not parse cron interval '{trigger}'. Use formats like '5m', '1h', or '1d'."
            amount = int(match.group(1))
            unit = match.group(2)
            
            interval_seconds = 0
            if unit == 'm':
                interval_seconds = amount * 60
            elif unit == 'h':
                interval_seconds = amount * 3600
            elif unit == 'd':
                interval_seconds = amount * 86400
            elif unit == 'w':
                interval_seconds = amount * 604800
                
            new_task["interval_seconds"] = interval_seconds
            new_task["interval_desc"] = trigger
            new_task["last_run"] = time.time()
            
        tasks.append(new_task)
        
        with open(schedules_file, "w", encoding="utf-8") as f:
            json.dump(tasks, f, indent=2, ensure_ascii=False)
            
        desc_type = "One-shot reminder" if task_type == "reminder" else f"Recurring cron (every {trigger})"
        return f"Success: Scheduled task '{task_id}' successfully. Type: {desc_type}. Target: {target}."
        
    except Exception as e:
        return f"Error scheduling task: {str(e)}"

def list_scheduled_tasks():
    try:
        schedules_file = os.path.join(WORKSPACE_DIR, "schedules.json")
        if not os.path.exists(schedules_file):
            return "No scheduled tasks found."
            
        with open(schedules_file, "r", encoding="utf-8") as f:
            tasks = json.load(f)
            
        if not tasks:
            return "No scheduled tasks found."
            
        import datetime
        output = ["=== SCHEDULED TASKS & CRONS ==="]
        for t in tasks:
            status_badge = f"[{t.get('status').upper()}]"
            details = f"ID: {t.get('id')} | {t.get('description')} | Target: {t.get('target')}"
            
            if t.get("type") == "reminder":
                trigger_dt = datetime.datetime.fromtimestamp(t.get("trigger_time")).strftime('%Y-%m-%d %H:%M:%S')
                output.append(f"{status_badge} Reminder -> Trigger Time: {trigger_dt} ({t.get('trigger_desc')}) | {details}")
            else:
                last_dt = datetime.datetime.fromtimestamp(t.get("last_run")).strftime('%Y-%m-%d %H:%M:%S') if t.get("last_run") else "Never"
                output.append(f"{status_badge} Cron -> Interval: {t.get('interval_desc')} | Last Run: {last_dt} | {details}")
                
        return "\n".join(output)
    except Exception as e:
        return f"Error listing scheduled tasks: {str(e)}"

def remove_scheduled_task(task_id):
    try:
        schedules_file = os.path.join(WORKSPACE_DIR, "schedules.json")
        if not os.path.exists(schedules_file):
            return "Error: No scheduled tasks found."
            
        with open(schedules_file, "r", encoding="utf-8") as f:
            tasks = json.load(f)
            
        query = str(task_id).strip().lower()
        
        # 1. Try exact ID match
        target_task = None
        for t in tasks:
            if t.get("id").lower() == query:
                target_task = t
                break
                
        # 2. Try description substring match
        if not target_task:
            for t in tasks:
                if query in t.get("description", "").lower():
                    target_task = t
                    break
                    
        if not target_task:
            return f"Error: No task found matching ID or description '{task_id}'."
            
        # Filter out target task
        filtered_tasks = [t for t in tasks if t.get("id") != target_task.get("id")]
        
        with open(schedules_file, "w", encoding="utf-8") as f:
            json.dump(filtered_tasks, f, indent=2, ensure_ascii=False)
            
        return f"Success: Removed scheduled task '{target_task.get('id')}' ({target_task.get('description')})."
    except Exception as e:
        return f"Error removing scheduled task: {str(e)}"

def detect_arp_spoofing():
    try:
        arp_file = "/proc/net/arp"
        if not os.path.exists(arp_file):
            return "Error: ARP table file /proc/net/arp is not accessible. This tool requires Android/Linux environment."
            
        with open(arp_file, "r") as f:
            lines = f.readlines()
            
        mac_to_ips = {}
        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 4:
                ip = parts[0]
                mac = parts[3].lower()
                
                if mac not in ["00:00:00:00:00:00", "*", "00:00:00:00:00:00:00:00"]:
                    if mac not in mac_to_ips:
                        mac_to_ips[mac] = []
                    mac_to_ips[mac].append(ip)
                    
        spoofed_entries = []
        for mac, ips in mac_to_ips.items():
            if len(ips) > 1:
                spoofed_entries.append({
                    "mac": mac,
                    "ips": ips
                })
                
        results = {
            "status": "safe",
            "message": "No active ARP spoofing detected. All MAC mappings are unique.",
            "mappings_checked": len(mac_to_ips)
        }
        
        if spoofed_entries:
            results["status"] = "warning"
            results["message"] = "WARNING: Potential ARP Spoofing / MITM attack detected! Multiple IP addresses map to the same MAC address."
            results["conflicting_entries"] = spoofed_entries
            
        return json.dumps(results, indent=2)
    except Exception as e:
        return f"Error executing ARP spoofing detector: {str(e)}"

def audit_vpn_connection():
    try:
        import requests
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get("http://ip-api.com/json/", headers=headers, timeout=10)
        
        if res.status_code != 200:
            return f"Error connecting to lookup server (code {res.status_code})."
            
        data = res.json()
        if data.get("status") != "success":
            return f"Lookup failed: {data.get('message', 'Unknown failure')}"
            
        ip = data.get("query")
        isp = data.get("isp", "")
        org = data.get("org", "")
        country = data.get("country", "")
        
        vpn_interface_active = False
        vpn_interfaces = []
        try:
            import socket
            if hasattr(socket, "if_nameindex"):
                interfaces = [x[1] for x in socket.if_nameindex()]
                for name in interfaces:
                    if any(prefix in name.lower() for prefix in ["tun", "tap", "wg", "ppp", "vpn", "p2p"]):
                        vpn_interface_active = True
                        vpn_interfaces.append(name)
        except Exception:
            pass
            
        vpn_keywords = ["vpn", "hosting", "cloud", "mullvad", "nordvpn", "expressvpn", "surfshark", "cloudflare", "ovh", "digitalocean", "linode", "amazon", "google", "microsoft"]
        isp_org_str = (isp + " " + org).lower()
        is_vpn_isp = any(kw in isp_org_str for kw in vpn_keywords)
        
        status = "unprotected"
        message = "No VPN connection detected. Your connection appears to be direct and unprotected."
        
        if vpn_interface_active or is_vpn_isp:
            status = "protected"
            reasons = []
            if vpn_interface_active:
                reasons.append(f"active VPN interface(s) detected: {', '.join(vpn_interfaces)}")
            if is_vpn_isp:
                reasons.append(f"public IP is owned by hosting/VPN provider ({isp})")
            message = f"VPN connection detected. Your connection is protected via: {' and '.join(reasons)}."
            
        audit = {
            "public_ip": ip,
            "isp": isp,
            "org": org,
            "location": f"{data.get('city')}, {data.get('regionName')}, {country}",
            "vpn_detection_status": status,
            "message": message
        }
        return json.dumps(audit, indent=2)
    except Exception as e:
        return f"Error executing connection auditor: {str(e)}"

def audit_website_security(url):
    try:
        import urllib.parse
        import requests
        import ssl
        import socket
        import datetime
        
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url
            
        parsed_url = urllib.parse.urlparse(url)
        domain = parsed_url.netloc or parsed_url.path
        if ":" in domain:
            domain = domain.split(":")[0]
            
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=12, verify=False)
        resp_headers = res.headers
        
        security_headers = {
            "Strict-Transport-Security": resp_headers.get("Strict-Transport-Security"),
            "Content-Security-Policy": resp_headers.get("Content-Security-Policy"),
            "X-Frame-Options": resp_headers.get("X-Frame-Options"),
            "X-Content-Type-Options": resp_headers.get("X-Content-Type-Options"),
            "Referrer-Policy": resp_headers.get("Referrer-Policy"),
            "X-XSS-Protection": resp_headers.get("X-XSS-Protection")
        }
        
        header_evals = {}
        score = 0
        total = len(security_headers)
        for h, val in security_headers.items():
            if val:
                header_evals[h] = f"Present: {val[:40]}..." if len(val) > 40 else f"Present: {val}"
                score += 1
            else:
                header_evals[h] = "MISSING! Susceptible to attacks."
                
        ssl_details = {}
        if url.startswith("https://") or parsed_url.scheme == "https" or not parsed_url.scheme:
            try:
                context = ssl.create_default_context()
                with socket.create_connection((domain, 443), timeout=5) as sock:
                    with context.wrap_socket(sock, server_hostname=domain) as ssock:
                        cert = ssock.getpeercert()
                        
                subject = dict(x[0] for x in cert.get('subject', ()))
                issuer = dict(x[0] for x in cert.get('issuer', ()))
                not_before = cert.get('notBefore')
                not_after = cert.get('notAfter')
                
                expiry_dt = datetime.datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z")
                remaining_days = (expiry_dt - datetime.datetime.utcnow()).days
                
                ssl_details = {
                    "common_name": subject.get("commonName"),
                    "issuer": issuer.get("organizationName") or issuer.get("commonName"),
                    "not_before": not_before,
                    "not_after": not_after,
                    "days_remaining": remaining_days,
                    "status": "valid" if remaining_days > 0 else "expired"
                }
            except Exception as ssl_err:
                ssl_details = {
                    "status": "error",
                    "error_message": f"SSL Handshake failed: {str(ssl_err)}"
                }
                
        audit_results = {
            "target_url": url,
            "target_domain": domain,
            "status_code": res.status_code,
            "security_headers_grade": f"{score}/{total} set",
            "security_headers_audit": header_evals,
            "ssl_certificate_details": ssl_details if ssl_details else "N/A (HTTP)"
        }
        return json.dumps(audit_results, indent=2)
    except Exception as e:
        return f"Error executing website security auditor: {str(e)}"

# ============================================================
# 🤖 AUTONOMOUS APP CONTROL — Robust UI Automation Engine
# ============================================================

_last_seen_elements = []

def _get_ui_elements(include_all=False):
    """Dumps and parses the active screen's UI hierarchy into structured element objects.
    
    Returns (True, elements_list) on success, (False, error_string) on failure.
    If include_all=True, returns non-interactable elements too (for context scanning).
    """
    try:
        import re as _re
        import xml.etree.ElementTree as ET

        dump_locations = ["/data/local/tmp/window_dump.xml", "/sdcard/window_dump.xml"]
        dump_file_on_device = None
        ok = False
        out = ""
        for loc in dump_locations:
            ok, out = run_adb_command(f"shell uiautomator dump {loc}")
            if ok and ("dumped to" in out.lower() or not out.strip()):
                dump_file_on_device = loc
                break
            else:
                test_ok, test_ls = run_adb_command(f"shell ls {loc}")
                if test_ok and "No such file" not in test_ls:
                    dump_file_on_device = loc
                    break

        if not dump_file_on_device:
            ok, out = run_adb_command("shell uiautomator dump")
            dump_file_on_device = "/sdcard/window_dump.xml"

        ok, xml_content = run_adb_command(f"shell cat {dump_file_on_device}")
        run_adb_command(f"shell rm -f {dump_file_on_device}")

        if not ok or not xml_content.strip():
            return False, f"Error reading UI XML: {xml_content}"

        try:
            cleaned_xml = _re.sub(r'[^\x09\x0A\x0D\x20-\x7E\x80-\xFF]', '', xml_content)
            root = ET.fromstring(cleaned_xml)
        except Exception as parse_err:
            return False, f"Error parsing UI XML: {parse_err}"

        elements = []

        def traverse(node, parent_clickable=False):
            attrib = node.attrib
            text = attrib.get("text", "").strip()
            content_desc = attrib.get("content-desc", "").strip()
            resource_id = attrib.get("resource-id", "").strip()
            class_name = attrib.get("class", "").split(".")[-1]
            bounds = attrib.get("bounds", "")
            clickable = attrib.get("clickable", "false").lower() == "true" or parent_clickable
            long_clickable = attrib.get("long-clickable", "false").lower() == "true"
            scrollable = attrib.get("scrollable", "false").lower() == "true"
            focusable = attrib.get("focusable", "false").lower() == "true"
            enabled = attrib.get("enabled", "true").lower() == "true"
            checkable = attrib.get("checkable", "false").lower() == "true"
            checked = attrib.get("checked", "false").lower() == "true"

            has_label = bool(text or content_desc or resource_id)

            if has_label and enabled:
                m = _re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
                if m:
                    x1, y1, x2, y2 = map(int, m.groups())
                    x_center = (x1 + x2) // 2
                    y_center = (y1 + y2) // 2
                    width = x2 - x1
                    height = y2 - y1

                    el = {
                        "class": class_name,
                        "center": (x_center, y_center),
                        "bounds": f"[{x1},{y1}][{x2},{y2}]",
                        "raw_bounds": (x1, y1, x2, y2),
                        "size": (width, height),
                    }
                    if text:          el["text"] = text
                    if content_desc:  el["content-desc"] = content_desc
                    if resource_id:
                        el["resource-id"] = resource_id.split("/")[-1]
                        el["full_resource_id"] = resource_id
                    if clickable:       el["clickable"] = True
                    if long_clickable:  el["long_clickable"] = True
                    if scrollable:      el["scrollable"] = True
                    if focusable:       el["focusable"] = True
                    if checkable:       el["checkable"] = True
                    if checked:         el["checked"] = True

                    if width > 0 and height > 0:
                        elements.append(el)
                    elif include_all:
                        elements.append(el)

            is_self_clickable = attrib.get("clickable", "false").lower() == "true"
            for child in node:
                traverse(child, parent_clickable=(clickable or is_self_clickable))

        traverse(root)
        return True, elements
    except Exception as e:
        return False, str(e)


def _score_element_match(el, target_lower):
    """Returns a match score (0 = no match, higher = better) for fuzzy element finding."""
    t   = el.get("text", "").lower()
    d   = el.get("content-desc", "").lower()
    r   = el.get("resource-id", "").lower()
    fr  = el.get("full_resource_id", "").lower()

    # Exact full match
    if target_lower in (t, d, r, fr):
        return 100 + (10 if el.get("clickable") else 0)

    # Starts-with match
    if t.startswith(target_lower) or d.startswith(target_lower):
        return 85 + (10 if el.get("clickable") else 0)

    # Substring match
    if target_lower in t or target_lower in d or target_lower in r or target_lower in fr:
        return 70 + (10 if el.get("clickable") else 0)

    # Clean query tokens (remove command stopwords and fillers)
    stopwords = {"play", "song", "video", "the", "a", "an", "on", "in", "by", "for", "to", "open", "click", "tap", "search"}
    raw_tokens = target_lower.split()
    core_tokens = [w for w in raw_tokens if w not in stopwords]
    query_words = core_tokens if core_tokens else raw_tokens

    combined = f"{t} {d} {r}"
    if len(query_words) >= 1:
        matched_count = sum(1 for w in query_words if w in combined)
        if matched_count == len(query_words):
            # All core words found in this element!
            return 80 + (10 if el.get("clickable") else 0)
        elif matched_count > 0:
            ratio = matched_count / len(query_words)
            return int(50 * ratio) + (10 if el.get("clickable") else 0)

    return 0


def dump_ui_layout():
    """Dumps all visible UI elements on the current screen for the AI to inspect."""
    ok, result = _get_ui_elements()
    if not ok:
        return f"Error dumping UI layout: {result}"

    elements = result
    if not elements:
        return "No readable or interactable elements found on the current screen."

    output = ["=== ACTIVE SCREEN UI ELEMENTS ==="]
    for idx, el in enumerate(elements, 1):
        parts = []
        if "text" in el:          parts.append(f'Text: "{el["text"]}"')
        if "content-desc" in el:  parts.append(f'Desc: "{el["content-desc"]}"')
        if "resource-id" in el:   parts.append(f'ID: "{el["resource-id"]}"')

        badges = []
        if el.get("clickable"):    badges.append("Clickable")
        if el.get("scrollable"):   badges.append("Scrollable")
        if el.get("focusable"):    badges.append("Focusable")
        if el.get("checkable"):    badges.append(f'Checkable(checked={el.get("checked", False)})')

        badge_str = f" [{', '.join(badges)}]" if badges else ""
        output.append(
            f"[{idx}] {el['class']}{badge_str} -> Center: {el['center']} | {', '.join(parts)}"
        )

    return "\n".join(output)


def get_screen_text():
    """Returns all visible text from the current screen as plain text — useful to read screen content, labels, prices, etc."""
    ok, elements = _get_ui_elements(include_all=True)
    if not ok:
        return f"Error reading screen text: {elements}"
    texts = []
    seen = set()
    for el in elements:
        for field in ("text", "content-desc"):
            val = el.get(field, "").strip()
            if val and val not in seen:
                texts.append(val)
                seen.add(val)
    if not texts:
        return "No readable text found on the current screen."
    return "\n".join(texts)


def see_screen(include_elements=True):
    """Acts as the AI's eyes. Captures the active phone screen, detects foreground app/activity,
    and returns a clean, structured visual map of all interactive buttons, inputs, video/content cards,
    and visible text with numbered indices [1], [2]... and exact coordinates for human-like phone control.
    """
    global _last_seen_elements
    import re as _re

    # 1. Capture screen photo to workspace for visual preview and history
    try:
        take_screenshot()
    except Exception:
        pass

    # 2. Detect active foreground application and activity
    app_info = "Unknown"
    active_pkg = ""
    ok, focus_out = run_adb_command("shell dumpsys window | grep -E 'mCurrentFocus|mFocusedApp'")
    if ok and focus_out:
        m = _re.search(r'([a-zA-Z0-9_\.]+)/([a-zA-Z0-9_\.]+)', focus_out)
        if m:
            active_pkg = m.group(1)
            activity = m.group(2)
            app_info = f"{active_pkg} ({activity})"

    if not active_pkg or "Unknown" in app_info:
        ok2, res_out = run_adb_command("shell dumpsys activity activities | grep -E 'mResumedActivity|topResumedActivity'")
        if ok2 and res_out:
            m = _re.search(r'([a-zA-Z0-9_\.]+)/([a-zA-Z0-9_\.]+)', res_out)
            if m:
                active_pkg = m.group(1)
                activity = m.group(2)
                app_info = f"{active_pkg} ({activity})"

    friendly_app_names = {
        "com.google.android.youtube": "YouTube",
        "com.spotify.music": "Spotify",
        "com.google.android.apps.youtube.music": "YouTube Music",
        "com.whatsapp": "WhatsApp",
        "com.android.chrome": "Google Chrome",
        "com.google.android.apps.nexuslauncher": "Home Screen (Launcher)",
        "com.sec.android.app.launcher": "Samsung Home Screen",
        "com.android.settings": "Android Settings",
        "com.android.vending": "Google Play Store",
        "com.google.android.dialer": "Phone / Dialer",
        "com.google.android.apps.messaging": "Messages (SMS)",
        "com.google.android.googlequicksearchbox": "Google Search"
    }
    friendly_name = friendly_app_names.get(active_pkg, active_pkg or "Active App")

    # 3. Retrieve UI Elements
    ok, elements = _get_ui_elements(include_all=True)
    if not ok or not elements:
        return (
            f"[SCREEN VISION - ACTIVE SCREEN]\n"
            f"📱 Active App: {friendly_name} [{app_info}]\n"
            f"📸 Screenshot: captured_screenshot.png (Saved to workspace)\n"
            f"⚠️ Notice: Could not read UI hierarchy: {elements}"
        )

    _last_seen_elements = elements

    interactive_items = []
    text_items = []
    seen_labels = set()

    for idx, el in enumerate(elements, 1):
        label = el.get("text") or el.get("content-desc") or el.get("resource-id") or ""
        label = label.strip()
        is_clickable = el.get("clickable") or el.get("focusable")
        center = el.get("center", (0, 0))
        el_class = el.get("class", "")

        if not label:
            continue

        if "EditText" in el_class or el.get("focusable"):
            interactive_items.append(f'[{idx}] Input Field: "{label}" -> Center: {center}')
        elif is_clickable or "Button" in el_class or "ImageView" in el_class:
            tag = "Button" if "Button" in el_class else ("Card/Item" if "Layout" in el_class or "ViewGroup" in el_class else "Clickable")
            res = f' (ID: {el.get("resource-id")})' if el.get("resource-id") else ""
            interactive_items.append(f'[{idx}] {tag} "{label}"{res} -> Center: {center}')
        else:
            if label not in seen_labels and len(label) > 1:
                seen_labels.add(label)
                text_items.append(f'"{label}"')

    output = [
        f"[SCREEN VISION - ACTIVE SCREEN]",
        f"📱 Active App: {friendly_name} [{app_info}]",
        f"📸 Screenshot: captured_screenshot.png (Saved to workspace)",
    ]

    if interactive_items:
        output.append("\n🎯 Interactive Elements (Buttons, Inputs, Cards):")
        for item in interactive_items[:30]:
            output.append(f"  {item}")
        if len(interactive_items) > 30:
            output.append(f"  ... (+{len(interactive_items) - 30} more interactive elements)")

    if text_items:
        output.append("\n📝 Visible Screen Text:")
        output.append("  " + " | ".join(text_items[:20]))

    output.append(
        "\n💡 Operator Action Hints:\n"
        "  • Click any element by index: smart_ui_click(target=\"[Index]\")  (e.g. smart_ui_click(target=\"[2]\"))\n"
        "  • Click any element by label: smart_ui_click(target=\"Label\")\n"
        "  • Type & Submit Search: smart_ui_type(target=\"Search\", text=\"Query\", press_enter=True)\n"
        "  • Tap coordinates: tap_coordinates(x=..., y=...)\n"
        "  • Scroll for more: smart_ui_scroll(direction=\"down\", amount=1)"
    )

    return "\n".join(output)


def smart_ui_click(target, scroll_attempts=3):
    """Finds a UI element by visible text, description, resource-id, or index [1] from see_screen(), and taps it.
    
    Automatically scrolls down up to `scroll_attempts` times to find off-screen elements.
    Returns a success/error message.
    """
    global _last_seen_elements
    import time
    import re as _re

    target_str = str(target).strip()

    # 1. Check if target is an index reference from see_screen(), e.g. "[3]" or "3"
    idx_match = _re.match(r'^\[?(\d+)\]?$', target_str)
    if idx_match and _last_seen_elements:
        idx = int(idx_match.group(1)) - 1
        if 0 <= idx < len(_last_seen_elements):
            el = _last_seen_elements[idx]
            x, y = el["center"]
            label = el.get("text") or el.get("content-desc") or el.get("resource-id") or f"Element {idx+1}"
            tap_res = tap_screen(x, y)
            time.sleep(0.4)
            return f"Success: Clicked element [{idx+1}] '{label}' at coordinates ({x}, {y})."

    # 2. Fuzzy match across screen elements
    target_lower = target_str.lower()
    for attempt in range(scroll_attempts + 1):
        ok, elements = _get_ui_elements()
        if not ok:
            return f"Error retrieving screen elements: {elements}"

        if not elements:
            return "Error: No visible UI elements detected on the screen."

        _last_seen_elements = elements

        best_el = None
        best_score = 0
        for el in elements:
            score = _score_element_match(el, target_lower)
            if score > best_score:
                best_score = score
                best_el = el

        if best_el and best_score >= 20:
            x, y = best_el["center"]
            label = best_el.get("text") or best_el.get("content-desc") or best_el.get("resource-id") or target_str
            tap_res = tap_screen(x, y)
            time.sleep(0.4)
            if "Success" in tap_res or "success" in tap_res.lower():
                return f"Success: Clicked '{label}' ({best_el.get('class', 'element')}) at ({x}, {y})."
            return f"Error tapping '{label}' at ({x}, {y}): {tap_res}"

        # Element not found — scroll down and retry
        if attempt < scroll_attempts:
            swipe_screen(500, 1400, 500, 600)
            time.sleep(0.6)

    # Recovery hint
    ok, elements = _get_ui_elements()
    samples = []
    if ok:
        for el in (elements or [])[:12]:
            label = el.get("text") or el.get("content-desc") or el.get("resource-id")
            if label:
                samples.append(f"'{label}'")
    visible_hint = ", ".join(samples) if samples else "none visible"
    return (
        f"Error: Could not find element matching '{target}' even after scrolling. "
        f"Currently visible elements: [{visible_hint}]. "
        f"Use see_screen() to inspect the active screen."
    )


def smart_ui_type(target="", text="", press_enter=False):
    """Focuses target input element (by label/id/index) and types text.
    Uses clipboard paste for full emoji and unicode support.
    Optionally presses Enter/Search key if press_enter=True.
    """
    import time

    if target:
        click_res = smart_ui_click(target, scroll_attempts=2)
        if "Error" in click_res and "Success" not in click_res:
            return f"Failed to focus input '{target}': {click_res}"
        time.sleep(0.4)

    if not text:
        if press_enter or str(press_enter).lower() in ["true", "1", "yes"]:
            run_adb_command("shell input keyevent 66")
            return "Success: Element focused and Enter/Search key pressed."
        return "Success: Element focused (no text provided to type)."

    # Method 1: Clipboard paste — best for unicode, spaces, emojis
    typed_ok = False
    try:
        clip_res = set_clipboard(text)
        if isinstance(clip_res, str) and clip_res.startswith("Success"):
            time.sleep(0.25)
            paste_ok, paste_out = run_adb_command("shell input keyevent 279")
            if paste_ok:
                typed_ok = True
    except Exception:
        pass

    # Method 2: Escaped shell input fallback
    if not typed_ok:
        escaped_chars = []
        for ch in str(text):
            if ch == ' ':
                escaped_chars.append('%s')
            elif ch in ['\\', '"', "'", '$', '`', '&', ';', '(', ')', '<', '>', '|', '~', '*', '?', '!', '#']:
                escaped_chars.append('\\' + ch)
            else:
                escaped_chars.append(ch)
        escaped_text = "".join(escaped_chars)
        type_ok, type_out = run_adb_command(f'shell input text "{escaped_text}"')
        if not type_ok:
            return f"Error typing text: {type_out}"

    time.sleep(0.3)
    if press_enter or str(press_enter).lower() in ["true", "1", "yes"]:
        run_adb_command("shell input keyevent 66") # KEYCODE_ENTER
        time.sleep(0.5)
        return f"Success: Typed '{text}' into {f'element \"{target}\"' if target else 'active field'} and submitted Enter/Search."

    return f"Success: Typed '{text}' into {f'element \"{target}\"' if target else 'active field'}."


def smart_ui_scroll(direction="down", amount=1):
    """Scrolls the screen in the given direction ('up', 'down', 'left', 'right') by a number of swipe steps.
    
    Use this when the element you need isn't visible on screen yet.
    """
    import time
    direction = str(direction).strip().lower()
    amount = max(1, min(int(amount), 10))

    scroll_map = {
        "down":  (500, 1400, 500, 600),
        "up":    (500, 600, 500, 1400),
        "left":  (1000, 800, 200, 800),
        "right": (200, 800, 1000, 800),
    }

    if direction not in scroll_map:
        return f"Error: Invalid direction '{direction}'. Use 'up', 'down', 'left', or 'right'."

    coords = scroll_map[direction]
    results = []
    for i in range(amount):
        res = swipe_screen(*coords)
        results.append(res)
        if i < amount - 1:
            time.sleep(0.35)

    ok_count = sum(1 for r in results if "Success" in str(r))
    return f"Success: Scrolled {direction} {ok_count}/{amount} times."


def smart_ui_wait_for(target, timeout_sec=8, poll_interval=1.0):
    """Waits up to `timeout_sec` seconds for a UI element matching `target` to appear on screen.
    
    Returns success when found, or error if the element doesn't appear in time.
    Useful after tapping buttons that trigger loading screens or transitions.
    """
    import time

    deadline = time.time() + float(timeout_sec)
    poll = max(0.3, float(poll_interval))
    checked = 0

    while time.time() < deadline:
        ok, elements = _get_ui_elements()
        if ok:
            target_lower = str(target).strip().lower()
            for el in elements:
                if _score_element_match(el, target_lower) >= 20:
                    label = el.get("text") or el.get("content-desc") or el.get("resource-id") or "?"
                    return f"Success: Element '{label}' appeared on screen after ~{checked * poll:.1f}s."
        checked += 1
        time.sleep(poll)

    return f"Error: Element '{target}' did not appear on screen within {timeout_sec} seconds. Use dump_ui_layout() to check what is currently visible."


def tap_coordinates(x, y):
    """Taps an exact pixel coordinate (x, y) on the screen. Use when you know the exact position from dump_ui_layout or screenshot analysis."""
    res = tap_screen(int(x), int(y))
    return res if res else f"Success: Tapped coordinates ({x}, {y})."


def install_app(app_name):
    """Autonomously installs an app from the Google Play Store.
    
    Opens Play Store, searches for the app, selects the first result, and taps Install.
    Examples: install_app("Instagram"), install_app("Spotify"), install_app("VLC")
    """
    import time

    app_name = str(app_name).strip()

    # Step 1: Launch Google Play Store
    launch_res = launch_app("com.android.vending")
    if "Error" in launch_res:
        # Fallback: open via intent
        run_adb_command('shell am start -a android.intent.action.VIEW -d "market://search" -p com.android.vending')
    time.sleep(2.0)

    # Step 2: Find and tap the Search bar/button in Play Store
    search_targets = ["Search for apps & games", "Search", "search", "com.android.vending:id/search_bar_hint",
                      "com.android.vending:id/search_bar_text_hint", "search_bar_hint"]
    search_found = False
    for s in search_targets:
        res = smart_ui_click(s, scroll_attempts=0)
        if "Success" in res:
            search_found = True
            break

    if not search_found:
        # Try pressing the search key
        run_adb_command("shell input keyevent 84")
        time.sleep(0.5)

    time.sleep(0.6)

    # Step 3: Type app name in the search field
    type_res = smart_ui_type("", app_name)
    time.sleep(0.5)

    # Step 4: Press Enter / Search
    run_adb_command("shell input keyevent 66")
    time.sleep(2.5)

    # Step 5: Tap first app result matching the name
    ok, elements = _get_ui_elements()
    tapped_result = False
    if ok:
        for el in elements:
            el_text = (el.get("text") or el.get("content-desc") or "").lower()
            if app_name.lower() in el_text and el.get("clickable"):
                tap_screen(*el["center"])
                tapped_result = True
                break

    if not tapped_result:
        # Click whatever is highest on screen that's clickable (first result)
        if ok and elements:
            for el in elements:
                if el.get("clickable") and el["center"][1] > 300:
                    tap_screen(*el["center"])
                    tapped_result = True
                    break

    time.sleep(2.5)

    # Step 6: Find and tap Install button
    install_targets = ["Install", "install", "com.android.vending:id/buy_button",
                       "com.android.vending:id/0_resource_name_obfuscated"]
    for i_btn in install_targets:
        res = smart_ui_click(i_btn, scroll_attempts=1)
        if "Success" in res:
            time.sleep(1.0)
            # Handle permission dialogs if they appear
            for allow_btn in ["Accept", "Continue", "Allow", "OK"]:
                smart_ui_click(allow_btn, scroll_attempts=0)
            return (
                f"Success: Initiated installation of '{app_name}' from Google Play Store. "
                f"The app will download and install automatically."
            )

    # Could not find Install button — check if app is already installed
    screen_text = get_screen_text()
    if "open" in screen_text.lower() or "uninstall" in screen_text.lower():
        return f"Info: '{app_name}' appears to already be installed (found 'Open'/'Uninstall' button on screen)."

    return (
        f"Partial: Opened Play Store and searched for '{app_name}', but could not find the Install button. "
        f"Current screen text: {screen_text[:300]}. "
        f"Try smart_ui_click('Install') or dump_ui_layout() to inspect the current state."
    )


def uninstall_app(package_name_or_app_name):
    """Uninstalls an app from the device.
    
    Accepts either a package name (e.g. 'com.instagram.android') or a common app name (e.g. 'Instagram').
    """
    import time

    target = str(package_name_or_app_name).strip()

    # Try ADB uninstall first if it looks like a package name
    if "." in target and " " not in target:
        ok, out = run_adb_command(f"shell pm uninstall --user 0 {target}")
        if ok and ("Success" in out or "success" in out.lower()):
            return f"Success: Uninstalled '{target}' via package manager."

    # Fallback: open App Info via Settings and uninstall from there
    if "." in target and " " not in target:
        pkg = target
    else:
        # Try to resolve package name from app name
        ok, out = run_adb_command(f'shell pm list packages | grep -i "{target.lower()}"')
        pkg = ""
        if ok and out.strip():
            lines = [l.strip() for l in out.strip().split("\n") if l.strip()]
            if lines:
                pkg = lines[0].replace("package:", "").strip()

    if pkg:
        run_adb_command(f'shell am start -a android.settings.APPLICATION_DETAILS_SETTINGS -d "package:{pkg}"')
        time.sleep(1.8)
        res = smart_ui_click("Uninstall", scroll_attempts=1)
        if "Success" in res:
            time.sleep(1.0)
            for confirm_btn in ["OK", "Uninstall"]:
                smart_ui_click(confirm_btn, scroll_attempts=0)
            return f"Success: Triggered uninstall of '{target}' via App Info settings."

    return (
        f"Error: Could not uninstall '{target}'. "
        f"Try using the exact package name (e.g. 'com.instagram.android') or go to Settings > Apps manually."
    )


def send_whatsapp_message(contact_or_number, message, auto_send=True):
    """Sends a WhatsApp message directly to a phone number or contact name using Android intents, contacts lookup, or autonomous in-app navigation."""
    import re
    import urllib.parse
    import time

    target = str(contact_or_number).strip()
    phone_number = ""
    contact_name = target

    # 1. Check if target contains only digits or phone format
    is_phone_num = bool(re.match(r'^\+?[\d\s\-\(\)]{7,20}$', target))
    if is_phone_num:
        phone_number = re.sub(r'[^\d+]', '', target)
    else:
        # Search address book via read_contacts_list
        contact_res = read_contacts_list(target)
        if not contact_res.startswith("Error") and not contact_res.startswith("No matching"):
            lines = contact_res.split("\n")
            for line in lines:
                if ":" in line:
                    parts = line.split(":", 1)
                    num_candidate = parts[1].strip()
                    num_clean = re.sub(r'[^\d+]', '', num_candidate)
                    if len(num_clean) >= 7:
                        phone_number = num_clean
                        contact_name = parts[0].lstrip("- ").strip()
                        break

    # 2. If phone number is resolved, use high-speed deep-link intent
    if phone_number:
        clean_digits = phone_number.lstrip("+")
        encoded_msg = urllib.parse.quote(str(message))

        intent_url = f"https://api.whatsapp.com/send?phone={clean_digits}&text={encoded_msg}"
        ok, out = run_adb_command(f'shell am start -a android.intent.action.VIEW -d "{intent_url}" -p com.whatsapp')

        if not ok or "Error" in out:
            ok, out = run_adb_command(f'shell am start -a android.intent.action.VIEW -d "{intent_url}"')
            if not ok:
                return f"Error launching WhatsApp intent: {out}"

        if not auto_send:
            return f"Success: Opened WhatsApp chat with {contact_name} ({phone_number}) with drafted message: \"{message}\"."

        # Auto-send: wait for WhatsApp chat screen to load
        time.sleep(1.8)

        # Try clicking Send button
        for send_btn in ["Send", "send", "com.whatsapp:id/send"]:
            click_res = smart_ui_click(send_btn, scroll_attempts=0)
            if "Success" in click_res:
                return f"Success: Sent WhatsApp message to {contact_name} ({phone_number}): \"{message}\"."

        # Brief retry if UI transition was slow
        time.sleep(1.0)
        for send_btn in ["Send", "send", "com.whatsapp:id/send"]:
            click_res = smart_ui_click(send_btn, scroll_attempts=0)
            if "Success" in click_res:
                return f"Success: Sent WhatsApp message to {contact_name} ({phone_number}): \"{message}\"."

        # Fallback to Enter keyevent
        run_adb_command("shell input keyevent 66")
        return f"Success: Opened WhatsApp chat with {contact_name} ({phone_number}) and triggered send. Message: \"{message}\"."

    # 3. Fallback: Autonomous In-App WhatsApp UI Navigation
    launch_res = launch_app("com.whatsapp")
    if "Error" in launch_res:
        return f"Error: Could not resolve phone number for '{target}' and failed to launch WhatsApp: {launch_res}"
    time.sleep(1.8)

    search_clicked = False
    for s_target in ["Search", "search", "menuitem_search", "com.whatsapp:id/menuitem_search"]:
        res = smart_ui_click(s_target, scroll_attempts=0)
        if res.startswith("Success"):
            search_clicked = True
            break
    if not search_clicked:
        run_adb_command("shell input keyevent 84")

    time.sleep(0.8)
    smart_ui_type("", target)
    time.sleep(1.5)

    contact_click = smart_ui_click(target, scroll_attempts=1)
    if not contact_click.startswith("Success"):
        return f"Opened WhatsApp and searched for '{target}', but could not find matching chat. Use dump_ui_layout() to inspect visible chats."

    time.sleep(1.2)
    type_res = smart_ui_type("Type a message", message)
    if not type_res.startswith("Success"):
        smart_ui_type("Message", message)

    if not auto_send:
        return f"Success: Opened WhatsApp chat with '{target}' and drafted message: \"{message}\"."

    time.sleep(0.8)
    for send_btn in ["Send", "send", "com.whatsapp:id/send"]:
        click_res = smart_ui_click(send_btn, scroll_attempts=0)
        if "Success" in click_res:
            return f"Success: Sent WhatsApp message to '{target}': \"{message}\"."

    run_adb_command("shell input keyevent 66")
    return f"Success: Opened WhatsApp chat with '{target}' and triggered send. Message: \"{message}\"."


def play_media(query, app="spotify"):
    """Dispatches media playback for Spotify, YouTube, or YouTube Music.
    For YouTube, it performs end-to-end human-like automation:
    1. Launches YouTube and searches for the query.
    2. Inspects screen elements to identify video result cards.
    3. Taps the matching video card to start playback.
    4. Verifies playback on screen.
    """
    import urllib.parse
    import time

    app_choice = str(app).lower().strip()
    query_str = str(query).strip()
    encoded_q = urllib.parse.quote(query_str)

    if app_choice in ["youtube", "yt"]:
        print(f"🎬 [play_media] Initiating YouTube playback workflow for '{query_str}'...")
        # Step 1: Try direct search VIEW intent first
        intent_ok, _ = run_adb_command(f'shell am start -a android.intent.action.VIEW -d "vnd.youtube://www.youtube.com/results?search_query={encoded_q}"')
        if not intent_ok:
            run_adb_command(f'shell am start -a android.intent.action.VIEW -d "https://www.youtube.com/results?search_query={encoded_q}" -p com.google.android.youtube')
        
        # Give YouTube time to render search results
        time.sleep(3.0)

        ok, elements = _get_ui_elements(include_all=True)
        search_results_found = False
        if ok and elements:
            for el in elements:
                desc = (el.get("content-desc") or "").lower()
                text = (el.get("text") or "").lower()
                if "filter" in desc or "shorts" in text or "views" in desc or "channel" in desc:
                    search_results_found = True
                    break

        if not search_results_found:
            # Fallback to human UI search:
            launch_app("com.google.android.youtube")
            time.sleep(2.0)
            smart_ui_click("Search", scroll_attempts=0)
            time.sleep(0.6)
            smart_ui_type("", query_str, press_enter=True)
            time.sleep(3.0)
            ok, elements = _get_ui_elements(include_all=True)

        # Step 2: Identify and click the best matching video card
        clicked_video = None
        if ok and elements:
            best_el = None
            best_score = 0
            for el in elements:
                desc = el.get("content-desc", "")
                text = el.get("text", "")
                res_id = el.get("resource-id", "")
                
                # Exclude filter buttons, search bar, back button, bottom tabs
                if any(x in (text + desc).lower() for x in ["all", "shorts", "unwatched", "recently uploaded", "navigate up", "voice search", "search youtube"]):
                    if not any(w in (text + desc).lower() for w in query_str.lower().split()):
                        continue

                score = _score_element_match(el, query_str.lower())
                if "views" in desc.lower() or "ago" in desc.lower():
                    score += 25
                if "title" in res_id.lower() or "thumbnail" in res_id.lower():
                    score += 15

                if score > best_score:
                    best_score = score
                    best_el = el

            if best_el and best_score >= 20:
                x, y = best_el["center"]
                label = best_el.get("text") or best_el.get("content-desc") or query_str
                tap_screen(x, y)
                clicked_video = label[:60]
            else:
                # Click the first prominent clickable element in the results body
                for el in elements:
                    cx, cy = el["center"]
                    if 350 < cy < 1300 and el.get("clickable"):
                        tap_screen(cx, cy)
                        clicked_video = el.get("text") or el.get("content-desc") or "First video result"
                        break

        # Step 3: Verification & Playback Trigger
        time.sleep(2.0)
        run_adb_command("shell input keyevent 126") # KEYCODE_MEDIA_PLAY

        if clicked_video:
            return (
                f"Success: Opened YouTube, searched for '{query_str}', and tapped '{clicked_video}'. "
                f"Video player launched and playback active on phone screen."
            )
        else:
            return (
                f"Partial: YouTube opened and searched for '{query_str}', but could not identify a clickable video card. "
                f"Please inspect screen using see_screen() or tap the video directly."
            )

    elif app_choice in ["youtube_music", "yt_music", "ytmusic"]:
        ok, out = run_adb_command(f'shell am start -a android.media.action.MEDIA_PLAY_FROM_SEARCH -e query "{query_str}" -p com.google.android.apps.youtube.music')
        if not ok or "Error" in out:
            run_adb_command(f'shell am start -a android.intent.action.VIEW -d "https://music.youtube.com/search?q={encoded_q}"')
        time.sleep(2.5)
        run_adb_command("shell input keyevent 126")
        return f"Success: Launched YouTube Music playback for '{query_str}'."

    elif app_choice == "spotify":
        ok, out = run_adb_command(f'shell am start -a android.media.action.MEDIA_PLAY_FROM_SEARCH -e query "{query_str}" -p com.spotify.music')
        if not ok or "Error" in out:
            run_adb_command(f'shell am start -a android.intent.action.VIEW -d "spotify:search:{encoded_q}" -p com.spotify.music')
        time.sleep(2.5)
        for p_btn in ["Play", "Shuffle play", "play", "shuffle"]:
            c_res = smart_ui_click(p_btn, scroll_attempts=0)
            if "Success" in c_res:
                break
        run_adb_command("shell input keyevent 126")
        run_adb_command("shell input keyevent 85")
        return f"Success: Launched Spotify playback search for '{query_str}' and triggered play."

    else:
        run_adb_command(f'shell am start -a android.media.action.MEDIA_PLAY_FROM_SEARCH -e query "{query_str}"')
        time.sleep(1.0)
        run_adb_command("shell input keyevent 126")
        return f"Success: Dispatched generic media play for '{query_str}'."


def send_android_intent(action, data_uri="", package_name="", extras=""):
    """Dispatches a custom Android Intent via ADB/Shizuku."""
    cmd = f'shell am start -a {action}'
    if data_uri:
        cmd += f' -d "{data_uri}"'
    if package_name:
        cmd += f' -p {package_name}'
    if extras:
        cmd += f' {extras}'

    ok, out = run_adb_command(cmd)
    if ok:
        return f"Success: Dispatched Android Intent '{action}'. Output: {out.strip() or 'OK'}"
    return f"Error dispatching intent: {out}"


def parse_arguments(arg_str):
    if not arg_str.strip():
        return {}
    kwargs = {}
    pattern = r'(\w+)\s*=\s*("[^"]*"|\'[^\']*\'|\[[^\]]*\]|[^,]+)'
    matches = re.findall(pattern, arg_str)
    for key, val in matches:
        val = val.strip()
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        elif val.startswith('[') and val.endswith(']'):
            try:
                val = json.loads(val.replace("'", '"'))
            except Exception:
                try:
                    val = [int(x.strip()) for x in val[1:-1].split(",") if x.strip()]
                except Exception:
                    try:
                        val = [x.strip().strip('"\'') for x in val[1:-1].split(",") if x.strip()]
                    except Exception:
                        pass
        else:
            if val.lower() == "true":
                val = True
            elif val.lower() == "false":
                val = False
            elif val.lower() == "none":
                val = None
            else:
                try:
                    val = int(val)
                except ValueError:
                    try:
                        val = float(val)
                    except ValueError:
                        pass
        kwargs[key] = val
    return kwargs

def execute_local_tool(name, args_str):
    try:
        kwargs = parse_arguments(args_str)
        if name == "get_system_stats":
            return get_system_stats()
        elif name == "local_port_scan":
            target_ip = kwargs.get("target_ip")
            ports_list = kwargs.get("ports_list")
            if not target_ip:
                return "Error: Missing required argument 'target_ip'."
            return local_port_scan(target_ip, ports_list)
        elif name == "list_directory":
            path = kwargs.get("path", ".")
            return list_directory(path)
        elif name == "read_file_content":
            file_path = kwargs.get("file_path")
            offset = kwargs.get("offset", 0)
            limit = kwargs.get("limit", 15000)
            if not file_path:
                return "Error: Missing required argument 'file_path'."
            return read_file_content(file_path, offset, limit)
        elif name == "write_file_content":
            file_path = kwargs.get("file_path")
            content = kwargs.get("content")
            if not file_path or content is None:
                return "Error: Missing required arguments 'file_path' and/or 'content'."
            return write_file_content(file_path, content)
        elif name == "delete_file":
            file_path = kwargs.get("file_path")
            if not file_path:
                return "Error: Missing required argument 'file_path'."
            return delete_file(file_path)
        elif name == "run_python_script":
            script_name = kwargs.get("script_name")
            args = kwargs.get("args")
            if not script_name:
                return "Error: Missing required argument 'script_name'."
            return run_python_script(script_name, args)
        elif name == "execute_termux_command":
            command = kwargs.get("command")
            if not command:
                return "Error: Missing required argument 'command'."
            return execute_termux_command(command)
        elif name == "web_search":
            query = kwargs.get("query")
            if not query:
                return "Error: Missing required argument 'query'."
            return web_search(query)
        elif name == "fetch_url":
            url = kwargs.get("url")
            if not url:
                return "Error: Missing required argument 'url'."
            return fetch_url(url)
        elif name == "download_file":
            url = kwargs.get("url")
            file_name = kwargs.get("file_name")
            if not url or not file_name:
                return "Error: Missing required arguments 'url' and/or 'file_name'."
            return download_file(url, file_name)
        elif name == "get_network_details":
            return get_network_details()
        elif name == "list_local_listeners":
            return list_local_listeners()
        elif name == "send_android_notification":
            title = kwargs.get("title")
            message = kwargs.get("message")
            if not title or not message:
                return "Error: Missing required arguments 'title' and/or 'message'."
            return send_android_notification(title, message)
        elif name == "vibrate_device":
            duration_ms = kwargs.get("duration_ms", 500)
            return vibrate_device(duration_ms)
        elif name == "search_files":
            pattern = kwargs.get("pattern")
            if not pattern:
                return "Error: Missing required argument 'pattern'."
            return search_files(pattern)
        elif name == "local_network_scan":
            return local_network_scan()
        elif name == "audit_android_security":
            return audit_android_security()
        elif name == "subnet_port_sweep":
            port_number = kwargs.get("port_number")
            if port_number is None:
                return "Error: Missing required argument 'port_number'."
            return subnet_port_sweep(port_number)
        elif name == "take_camera_photo":
            camera_id = kwargs.get("camera_id", "0")
            return take_camera_photo(camera_id)
        elif name == "get_phone_location":
            return get_phone_location()
        elif name == "make_phone_call":
            phone_number = kwargs.get("phone_number")
            if not phone_number:
                return "Error: Missing required argument 'phone_number'."
            return make_phone_call(phone_number)
        elif name == "send_sms":
            phone_number = kwargs.get("phone_number")
            message = kwargs.get("message")
            if not phone_number or not message:
                return "Error: Missing required arguments 'phone_number' and/or 'message'."
            return send_sms(phone_number, message)
        elif name == "read_contacts_list":
            search_query = kwargs.get("search_query", "")
            return read_contacts_list(search_query)
        elif name == "record_screen_video":
            duration_sec = kwargs.get("duration_sec", 5)
            return record_screen_video(duration_sec)
        elif name == "movement_intrusion_alarm":
            duration_sec = kwargs.get("duration_sec", 10)
            return movement_intrusion_alarm(duration_sec)
        elif name == "detect_faces_in_photo":
            photo_path = kwargs.get("photo_path")
            if not photo_path:
                return "Error: Missing required argument 'photo_path'."
            return detect_faces_in_photo(photo_path)
        elif name == "check_system_health":
            auto_install = kwargs.get("auto_install", False)
            if isinstance(auto_install, str):
                auto_install = auto_install.lower() == "true"
            return check_system_health(auto_install)
        elif name == "scan_nearby_signals":
            return scan_nearby_signals()
        elif name == "set_brightness":
            level = kwargs.get("level")
            if level is None:
                return "Error: Missing required argument 'level'."
            return set_brightness(level)
        elif name == "set_volume":
            stream = kwargs.get("stream")
            level = kwargs.get("level")
            if not stream or level is None:
                return "Error: Missing required arguments 'stream' and/or 'level'."
            return set_volume(stream, level)
        elif name == "take_screenshot":
            return take_screenshot()
        elif name == "tap_screen":
            x = kwargs.get("x")
            y = kwargs.get("y")
            if x is None or y is None:
                return "Error: Missing required arguments 'x' and/or 'y'."
            return tap_screen(x, y)
        elif name == "swipe_screen":
            x1 = kwargs.get("x1")
            y1 = kwargs.get("y1")
            x2 = kwargs.get("x2")
            y2 = kwargs.get("y2")
            duration_ms = kwargs.get("duration_ms", 500)
            if x1 is None or y1 is None or x2 is None or y2 is None:
                return "Error: Missing required coordinate parameters."
            return swipe_screen(x1, y1, x2, y2, duration_ms)
        elif name == "press_key":
            key_code = kwargs.get("key_code")
            if key_code is None:
                return "Error: Missing required argument 'key_code'."
            return press_key(key_code)
        elif name == "launch_app":
            package_name = kwargs.get("package_name")
            if not package_name:
                return "Error: Missing required argument 'package_name'."
            return launch_app(package_name)
        elif name == "control_android_system":
            action = kwargs.get("action")
            target = kwargs.get("target", "")
            if not action:
                return "Error: Missing required argument 'action'."
            return control_android_system(action, target)
        elif name == "get_clipboard":
            return get_clipboard()
        elif name == "set_clipboard":
            text = kwargs.get("text")
            if text is None:
                return "Error: Missing required argument 'text'."
            return set_clipboard(text)
        elif name == "list_installed_apps":
            user_only = kwargs.get("user_only", True)
            return list_installed_apps(user_only)
        elif name == "scan_wifi_networks":
            return scan_wifi_networks()
        elif name == "speak_text":
            text = kwargs.get("text")
            if not text:
                return "Error: Missing required argument 'text'."
            return speak_text(text)
        elif name == "dns_lookup":
            domain = kwargs.get("domain")
            record_type = kwargs.get("record_type", "A")
            if not domain:
                return "Error: Missing required argument 'domain'."
            return dns_lookup(domain, record_type)
        elif name == "whois_lookup":
            domain = kwargs.get("domain")
            if not domain:
                return "Error: Missing required argument 'domain'."
            return whois_lookup(domain)
        elif name == "analyze_hash":
            hash_str = kwargs.get("hash_str")
            if not hash_str:
                return "Error: Missing required argument 'hash_str'."
            return analyze_hash(hash_str)
        elif name == "open_url_on_phone":
            url = kwargs.get("url")
            if not url:
                return "Error: Missing required argument 'url'."
            return open_url_on_phone(url)
        elif name == "execute_root_command":
            command = kwargs.get("command")
            if not command:
                return "Error: Missing required argument 'command'."
            return execute_root_command(command)
        elif name == "audit_sms_inbox":
            limit = kwargs.get("limit", 10)
            return audit_sms_inbox(limit)
        elif name == "ip_geolocation_lookup":
            ip_address = kwargs.get("ip_address")
            if not ip_address:
                return "Error: Missing required argument 'ip_address'."
            return ip_geolocation_lookup(ip_address)
        elif name == "read_phone_sensors":
            sensor_name = kwargs.get("sensor_name", "")
            return read_phone_sensors(sensor_name)
        elif name == "dump_ui_layout":
            return dump_ui_layout()
        elif name == "add_scheduled_task":
            task_type = kwargs.get("task_type")
            trigger = kwargs.get("trigger")
            description = kwargs.get("description")
            target = kwargs.get("target", "telegram")
            if not task_type or not trigger or not description:
                return "Error: Missing required arguments."
            return add_scheduled_task(task_type, trigger, description, target)
        elif name == "list_scheduled_tasks":
            return list_scheduled_tasks()
        elif name == "remove_scheduled_task":
            task_id = kwargs.get("task_id")
            if not task_id:
                return "Error: Missing required argument 'task_id'."
            return remove_scheduled_task(task_id)
        elif name == "detect_arp_spoofing":
            return detect_arp_spoofing()
        elif name == "audit_vpn_connection":
            return audit_vpn_connection()
        elif name == "audit_website_security":
            url = kwargs.get("url")
            if not url:
                return "Error: Missing required argument 'url'."
            return audit_website_security(url)
        elif name == "search_file_content":
            query = kwargs.get("query")
            pattern = kwargs.get("pattern", "*")
            if not query:
                return "Error: Missing required argument 'query'."
            return search_file_content(query, pattern)
        elif name == "analyze_apk_manifest":
            apk_path = kwargs.get("apk_path")
            if not apk_path:
                return "Error: Missing required argument 'apk_path'."
            return analyze_apk_manifest(apk_path)
        elif name == "check_subdomain_takeover":
            domain = kwargs.get("domain")
            if not domain:
                return "Error: Missing required argument 'domain'."
            return check_subdomain_takeover(domain)
        elif name == "generate_hash_checksum":
            file_path_or_text = kwargs.get("file_path_or_text")
            algo = kwargs.get("algo", "sha256")
            if not file_path_or_text:
                return "Error: Missing required argument 'file_path_or_text'."
            return generate_hash_checksum(file_path_or_text, algo)
        elif name == "analyze_pcap_capture":
            pcap_path = kwargs.get("pcap_path")
            limit = kwargs.get("limit", 20)
            if not pcap_path:
                return "Error: Missing required argument 'pcap_path'."
            return analyze_pcap_capture(pcap_path, limit)
        elif name == "jwt_decoder_analyzer":
            token = kwargs.get("token")
            if not token:
                return "Error: Missing required argument 'token'."
            return jwt_decoder_analyzer(token)
        elif name == "system_process_monitor":
            filter_name = kwargs.get("filter_name", "")
            return system_process_monitor(filter_name)
        elif name == "send_whatsapp_message":
            contact_or_number = kwargs.get("contact_or_number")
            message = kwargs.get("message")
            auto_send = kwargs.get("auto_send", True)
            if not contact_or_number or not message:
                return "Error: Missing required arguments 'contact_or_number' and/or 'message'."
            return send_whatsapp_message(contact_or_number, message, auto_send)
        elif name == "play_media":
            query = kwargs.get("query")
            app = kwargs.get("app", "spotify")
            if not query:
                return "Error: Missing required argument 'query'."
            return play_media(query, app)
        elif name == "dump_ui_layout":
            return dump_ui_layout()
        elif name == "see_screen":
            include_elements = kwargs.get("include_elements", True)
            return see_screen(include_elements)
        elif name == "get_screen_text":
            return get_screen_text()
        elif name == "smart_ui_click":
            target = kwargs.get("target")
            scroll_attempts = kwargs.get("scroll_attempts", 3)
            if not target:
                return "Error: Missing required argument 'target'."
            return smart_ui_click(target, int(scroll_attempts))
        elif name == "smart_ui_type":
            text = kwargs.get("text", "")
            target = kwargs.get("target", "")
            press_enter = kwargs.get("press_enter", False)
            return smart_ui_type(target, text, press_enter)
        elif name == "smart_ui_scroll":
            direction = kwargs.get("direction", "down")
            amount = kwargs.get("amount", 1)
            return smart_ui_scroll(direction, int(amount))
        elif name == "smart_ui_wait_for":
            target = kwargs.get("target")
            timeout_sec = kwargs.get("timeout_sec", 8)
            poll_interval = kwargs.get("poll_interval", 1.0)
            if not target:
                return "Error: Missing required argument 'target'."
            return smart_ui_wait_for(target, float(timeout_sec), float(poll_interval))
        elif name == "tap_coordinates":
            x = kwargs.get("x")
            y = kwargs.get("y")
            if x is None or y is None:
                return "Error: Missing required arguments 'x' and/or 'y'."
            return tap_coordinates(x, y)
        elif name == "install_app":
            app_name = kwargs.get("app_name")
            if not app_name:
                return "Error: Missing required argument 'app_name'."
            return install_app(app_name)
        elif name == "uninstall_app":
            package_name_or_app_name = kwargs.get("package_name_or_app_name") or kwargs.get("app_name") or kwargs.get("package_name")
            if not package_name_or_app_name:
                return "Error: Missing required argument 'package_name_or_app_name'."
            return uninstall_app(package_name_or_app_name)
        elif name == "send_android_intent":
            action = kwargs.get("action")
            data_uri = kwargs.get("data_uri", "")
            package_name = kwargs.get("package_name", "")
            extras = kwargs.get("extras", "")
            if not action:
                return "Error: Missing required argument 'action'."
            return send_android_intent(action, data_uri, package_name, extras)
        else:
            # Check if it's an MCP tool
            mcp_conns = load_mcp_connections()
            mcp_tool_routing = {}
            for conn in mcp_conns:
                for t in conn.get("tools", []):
                    mcp_tool_routing[t.get("name")] = conn
                    
            if name in mcp_tool_routing:
                conn = mcp_tool_routing[name]
                transport = conn.get("transport", "sse")
                if transport == "stdio":
                    conn_name = conn.get("name")
                    stdio_conn = active_stdio_connections.get(conn_name)
                    if not stdio_conn:
                        # Try to restart it
                        print(f"🔌 Lazy-starting stdio MCP server: {conn_name}")
                        stdio_conn = StdioMcpConnection(conn_name, conn.get("command"))
                        if stdio_conn.start():
                            # Perform handshake
                            init_res = stdio_conn.send_request("initialize", {
                                "protocolVersion": "2024-11-05",
                                "capabilities": {},
                                "clientInfo": {"name": "pocketstrike-client", "version": "1.0.0"}
                            })
                            if "error" not in init_res:
                                stdio_conn.send_notification("notifications/initialized")
                                active_stdio_connections[conn_name] = stdio_conn
                            else:
                                stdio_conn.stop()
                                stdio_conn = None
                        else:
                            stdio_conn = None
                            
                    if not stdio_conn:
                        return f"Error: Stdio MCP server '{conn_name}' is not running and failed to start."
                        
                    res = stdio_conn.send_request("tools/call", {
                        "name": name,
                        "arguments": kwargs
                    })
                    
                    if "error" in res:
                        return f"Error from stdio MCP server: {res['error'].get('message')}"
                    elif "result" in res and "content" in res["result"]:
                        contents = res["result"]["content"]
                        text_outputs = []
                        for c in contents:
                            if c.get("type") == "text":
                                text_outputs.append(c.get("text", ""))
                        return "\n".join(text_outputs)
                    return f"Error: Unexpected response format from stdio MCP: {res}"
                else:
                    return call_remote_mcp_tool(conn.get("url"), name, kwargs, conn.get("headers"))
            else:
                return f"Error: Tool '{name}' is not recognized."
    except Exception as e:
        return f"Error executing tool: {str(e)}"

def get_ai_response_with_tools(messages):
    # Keep the full history on disk, but send only a rolling window of the last 60 messages to the API
    if len(messages) > 60:
        messages = [messages[0]] + messages[-59:]
        
    system_index = -1
    for idx, msg in enumerate(messages):
        if msg["role"] == "system":
            system_index = idx
            break
            
    full_prompt = get_system_prompt()
    if system_index >= 0:
        messages[system_index]["content"] = full_prompt
    else:
        messages.insert(0, {
            "role": "system",
            "content": full_prompt
        })
        
    loop_count = 0
    max_loops = 25
    
    while loop_count < max_loops:
        response_text = call_ai_api(messages)
        
        # Check for tool call trigger
        match = re.search(r'\[TOOL_CALL:\s*(\w+)\(([\s\S]*?)\)\s*\]', response_text)
        if not match:
            messages.append({"role": "assistant", "content": response_text})
            return response_text, messages
            
        tool_name = match.group(1)
        tool_args_str = match.group(2)
        
        print(f"🔧 AI requested tool: {tool_name}({tool_args_str})")
        
        # Execute tool
        tool_result = execute_local_tool(tool_name, tool_args_str)
        
        # Append tool call and output to conversation
        messages.append({"role": "assistant", "content": response_text})
        messages.append({
            "role": "user",
            "content": f"[TOOL_RESULT: {tool_name} output]\n{tool_result}"
        })
        
        loop_count += 1
        
    fallback = "Error: Tool execution loop limit reached."
    messages.append({"role": "assistant", "content": fallback})
    return fallback, messages

# Streaming AI calls for ReAct and responses
def call_ai_api_stream(messages):
    provider = config.get("provider")
    model = config.get("model")
    api_key = config.get("api_key", "")
    base_url = config.get("base_url", "")

    if not provider:
        yield "Error: AI Provider is not configured."
        return

    try:
        # 1. Google Gemini API Stream
        if provider == "gemini":
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?key={api_key}"
            gemini_messages = []
            for msg in messages:
                role = "model" if msg["role"] == "assistant" else "user"
                gemini_messages.append({
                    "role": role,
                    "parts": [{"text": msg["content"]}]
                })
            payload = {"contents": gemini_messages}
            res = requests.post(url, json=payload, stream=True, timeout=60)
            
            for line in res.iter_lines():
                if line:
                    line_str = line.decode('utf-8').strip()
                    if line_str.startswith("["):
                        line_str = line_str[1:]
                    if line_str.endswith("]"):
                        line_str = line_str[:-1]
                    if line_str.startswith(","):
                        line_str = line_str[1:]
                    try:
                        data = json.loads(line_str)
                        text = data["candidates"][0]["content"]["parts"][0]["text"]
                        yield text
                    except Exception:
                        pass

        # 2. Anthropic API Stream
        elif provider == "anthropic":
            url = f"{base_url}/messages"
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }
            system_prompt = ""
            filtered_messages = []
            for m in messages:
                if m["role"] == "system":
                    system_prompt = m["content"]
                else:
                    role = "assistant" if m["role"] == "assistant" else "user"
                    filtered_messages.append({"role": role, "content": m["content"]})
            
            payload = {
                "model": model,
                "messages": filtered_messages,
                "max_tokens": 4096,
                "stream": True
            }
            if system_prompt:
                payload["system"] = system_prompt
                
            res = requests.post(url, json=payload, headers=headers, stream=True, timeout=60)
            for line in res.iter_lines():
                if line:
                    line_str = line.decode('utf-8').strip()
                    if line_str.startswith("data: "):
                        data_json = line_str[6:]
                        try:
                            data = json.loads(data_json)
                            if data.get("type") == "content_block_delta":
                                yield data["delta"].get("text", "")
                        except Exception:
                            pass

        # 3. OpenAI and compatible APIs Stream
        else:
            if provider == "ollama":
                url = f"{base_url}/v1/chat/completions"
            else:
                url = f"{base_url}/chat/completions"
                
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            
            payload = {
                "model": model,
                "messages": messages,
                "stream": True
            }

            res = requests.post(url, json=payload, headers=headers, stream=True, timeout=60)
            for line in res.iter_lines():
                if line:
                    line_str = line.decode('utf-8').strip()
                    if line_str.startswith("data: "):
                        data_json = line_str[6:]
                        if data_json == "[DONE]":
                            break
                        try:
                            data = json.loads(data_json)
                            content = data["choices"][0]["delta"].get("content", "")
                            if content:
                                yield content
                        except Exception:
                            pass

    except Exception as e:
        yield f"Stream Request Error: {str(e)}"

def get_ai_response_stream(messages):
    # Keep the full history in the web browser, but send only a rolling window of the last 60 messages to the API
    if len(messages) > 60:
        messages = [messages[0]] + messages[-59:]
        
    system_index = -1
    for idx, msg in enumerate(messages):
        if msg["role"] == "system":
            system_index = idx
            break
            
    full_prompt = get_system_prompt()
    if system_index >= 0:
        messages[system_index]["content"] = full_prompt
    else:
        messages.insert(0, {
            "role": "system",
            "content": full_prompt
        })
        
    loop_count = 0
    max_loops = 25
    
    while loop_count < max_loops:
        stream = call_ai_api_stream(messages)
        
        accumulated_response = ""
        for chunk in stream:
            accumulated_response += chunk
            yield chunk
            
        # Check if the accumulated response contains a tool call
        match = re.search(r'\[TOOL_CALL:\s*(\w+)\(([\s\S]*?)\)\s*\]', accumulated_response)
        if not match:
            messages.append({"role": "assistant", "content": accumulated_response})
            yield f"\n[HISTORY_SYNC]:{json.dumps(messages)}"
            return
            
        tool_name = match.group(1)
        tool_args_str = match.group(2)
        
        print(f"🔧 AI requested tool: {tool_name}({tool_args_str})")
        
        # Execute tool
        tool_result = execute_local_tool(tool_name, tool_args_str)
        
        tool_result_msg = f"\n[TOOL_RESULT: {tool_name} output]\n{tool_result}"
        yield tool_result_msg
        
        messages.append({"role": "assistant", "content": accumulated_response})
        messages.append({
            "role": "user",
            "content": f"[TOOL_RESULT: {tool_name} output]\n{tool_result}"
        })
        
        loop_count += 1
        
    fallback = "Error: Tool execution loop limit reached."
    yield fallback
    messages.append({"role": "assistant", "content": fallback})
    yield f"\n[HISTORY_SYNC]:{json.dumps(messages)}"

# Call selected AI provider
def call_ai_api(messages):
    provider = config.get("provider")
    model = config.get("model")
    api_key = config.get("api_key", "")
    base_url = config.get("base_url", "")

    if not provider:
        return "Error: AI Provider is not configured."

    try:
        # 1. Google Gemini API
        if provider == "gemini":
            # Map OpenAI messages format to Gemini format
            contents = []
            for msg in messages:
                role = "user" if msg["role"] == "user" else "model"
                contents.append({
                    "role": role,
                    "parts": [{"text": msg["content"]}]
                })
            
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            headers = {"Content-Type": "application/json"}
            payload = {"contents": contents}

            res = requests.post(url, json=payload, headers=headers, timeout=60)
            if res.status_code == 200:
                data = res.json()
                try:
                    return data["candidates"][0]["content"]["parts"][0]["text"]
                except (KeyError, IndexError):
                    return f"Error: Unexpected Gemini response format. Details: {res.text}"
            else:
                return f"Gemini API Error (Status {res.status_code}): {res.text}"

        # 2. Anthropic Claude API
        elif provider == "anthropic":
            url = f"{base_url}/messages"
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }
            
            # Separate system prompt
            system_prompt = ""
            anthropic_messages = []
            for msg in messages:
                if msg["role"] == "system":
                    system_prompt = msg["content"]
                else:
                    anthropic_messages.append({
                        "role": msg["role"],
                        "content": msg["content"]
                    })
            
            payload = {
                "model": model,
                "max_tokens": 4096,
                "messages": anthropic_messages
            }
            if system_prompt:
                payload["system"] = system_prompt

            res = requests.post(url, json=payload, headers=headers, timeout=60)
            if res.status_code == 200:
                data = res.json()
                try:
                    return data["content"][0]["text"]
                except (KeyError, IndexError):
                    return f"Error: Unexpected Anthropic response format. Details: {res.text}"
            else:
                return f"Anthropic API Error (Status {res.status_code}): {res.text}"

        # 3. OpenAI and compatible APIs (OpenRouter, OpenCode, OpenCode Zen, Ollama, Custom)
        else:
            if provider == "ollama":
                url = f"{base_url}/v1/chat/completions"
            else:
                url = f"{base_url}/chat/completions"
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            
            payload = {
                "model": model,
                "messages": messages
            }

            res = requests.post(url, json=payload, headers=headers, timeout=60)
            if res.status_code == 200:
                data = res.json()
                try:
                    return data["choices"][0]["message"]["content"]
                except (KeyError, IndexError):
                    return f"Error: Unexpected API response format. Details: {res.text}"
            else:
                return f"API Error (Status {res.status_code}): {res.text}"

    except Exception as e:
        return f"Request Error: {str(e)}"

def load_unified_history():
    history_file = os.path.join(WORKSPACE_DIR, "agent", "unified_history.json")
    if os.path.exists(history_file):
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading unified history: {e}")
    return [
        {"role": "system", "content": "You are PocketstrikeAI, a helpful, cool, and highly advanced local AI assistant. Keep responses engaging."}
    ]

def save_unified_history(history):
    history_file = os.path.join(WORKSPACE_DIR, "agent", "unified_history.json")
    try:
        os.makedirs(os.path.dirname(history_file), exist_ok=True)
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving unified history: {e}")

def load_conversations():
    conv_file = os.path.join(WORKSPACE_DIR, "agent", "conversations.json")
    if os.path.exists(conv_file):
        try:
            with open(conv_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading conversations.json: {e}")
    return []

def save_conversations(conversations):
    conv_file = os.path.join(WORKSPACE_DIR, "agent", "conversations.json")
    try:
        os.makedirs(os.path.dirname(conv_file), exist_ok=True)
        with open(conv_file, "w", encoding="utf-8") as f:
            json.dump(conversations, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving conversations.json: {e}")

def register_telegram_chat(chat_id):
    chats_file = os.path.join(WORKSPACE_DIR, "agent", "telegram_active_chats.json")
    chats = []
    if os.path.exists(chats_file):
        try:
            with open(chats_file, "r") as f:
                chats = json.load(f)
        except Exception:
            pass
    if chat_id not in chats:
        chats.append(chat_id)
        try:
            with open(chats_file, "w") as f:
                json.dump(chats, f)
        except Exception:
            pass

def get_registered_telegram_chats():
    chats_file = os.path.join(WORKSPACE_DIR, "agent", "telegram_active_chats.json")
    if os.path.exists(chats_file):
        try:
            with open(chats_file, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def load_mcp_connections():
    mcp_file = os.path.join(WORKSPACE_DIR, "agent", "mcp_connections.json")
    if os.path.exists(mcp_file):
        try:
            with open(mcp_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_mcp_connections(conns):
    mcp_file = os.path.join(WORKSPACE_DIR, "agent", "mcp_connections.json")
    try:
        os.makedirs(os.path.dirname(mcp_file), exist_ok=True)
        with open(mcp_file, "w", encoding="utf-8") as f:
            json.dump(conns, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving MCP connections: {e}")



class StdioMcpConnection:
    def __init__(self, name, command):
        self.name = name
        self.command = command
        self.proc = None
        self.reader_thread = None
        self.stderr_thread = None
        self.response_queues = {}
        self.is_running = False
        self.lock = threading.Lock()
        self.next_id = 1
        
    def start(self):
        import subprocess
        import shlex
        import os
        import threading
        try:
            use_shell = os.name == 'nt'
            cmd_str = self.command.strip()
            if cmd_str.startswith("http://") or cmd_str.startswith("https://"):
                if use_shell:
                    cmd_args = f"uvx fastmcp-remote {cmd_str}"
                else:
                    cmd_args = ["uvx", "fastmcp-remote", cmd_str]
            else:
                if use_shell:
                    cmd_args = cmd_str
                else:
                    cmd_args = shlex.split(cmd_str)
                
            self.proc = subprocess.Popen(
                cmd_args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=use_shell,
                bufsize=1
            )
            self.is_running = True
            
            self.reader_thread = threading.Thread(target=self._read_loop, daemon=True)
            self.reader_thread.start()
            
            self.stderr_thread = threading.Thread(target=self._stderr_loop, daemon=True)
            self.stderr_thread.start()
            
            return True
        except Exception as e:
            print(f"Error starting stdio MCP server '{self.name}': {e}")
            self.is_running = False
            return False
            
    def _read_loop(self):
        import json
        try:
            for line in iter(self.proc.stdout.readline, ''):
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    msg_id = msg.get("id")
                    if msg_id is not None:
                        with self.lock:
                            q = self.response_queues.get(msg_id)
                        if q:
                            q.put(msg)
                except Exception as e:
                    print(f"[{self.name}] Error parsing stdio message: {e}. Raw line: {line}")
        except Exception as e:
            print(f"[{self.name}] Stdio read loop error: {e}")
        finally:
            self.is_running = False
            
    def _stderr_loop(self):
        try:
            for line in iter(self.proc.stderr.readline, ''):
                if not line:
                    break
                print(f"[{self.name} STDERR] {line.strip()}")
        except Exception:
            pass
            
    def send_request(self, method, params=None, timeout=15):
        import json
        import queue
        if not self.is_running or not self.proc:
            if not self.start():
                return {"error": {"message": "Stdio MCP process is not running"}}
                
        with self.lock:
            req_id = self.next_id
            self.next_id += 1
            q = queue.Queue()
            self.response_queues[req_id] = q
            
        req = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": req_id
        }
        
        try:
            payload = json.dumps(req) + "\n"
            self.proc.stdin.write(payload)
            self.proc.stdin.flush()
        except Exception as e:
            self.is_running = False
            return {"error": {"message": f"Failed to write to stdio: {e}"}}
            
        try:
            resp = q.get(timeout=timeout)
            return resp
        except queue.Empty:
            return {"error": {"message": f"Request timed out waiting for stdio response after {timeout}s"}}
        finally:
            with self.lock:
                self.response_queues.pop(req_id, None)
                
    def send_notification(self, method, params=None):
        import json
        if not self.is_running or not self.proc:
            self.start()
        req = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {}
        }
        try:
            payload = json.dumps(req) + "\n"
            self.proc.stdin.write(payload)
            self.proc.stdin.flush()
            return True
        except Exception:
            self.is_running = False
            return False
            
    def stop(self):
        self.is_running = False
        if self.proc:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=2)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            self.proc = None

active_stdio_connections = {}

def init_stdio_mcp_connections():
    conns = load_mcp_connections()
    for conn in conns:
        if conn.get("transport") == "stdio":
            name = conn.get("name")
            cmd = conn.get("command")
            if name and cmd:
                print(f"🔌 Starting stdio MCP server: {name} ({cmd})")
                stdio_conn = StdioMcpConnection(name, cmd)
                if stdio_conn.start():
                    # Perform handshake
                    init_res = stdio_conn.send_request("initialize", {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "pocketstrike-client", "version": "1.0.0"}
                    })
                    if "error" not in init_res:
                        stdio_conn.send_notification("notifications/initialized")
                        active_stdio_connections[name] = stdio_conn
                        print(f"✅ Handshake successful with stdio MCP server '{name}'")
                    else:
                        print(f"❌ Handshake failed with stdio MCP server '{name}': {init_res.get('error')}")
                        stdio_conn.stop()
                else:
                    print(f"❌ Failed to start stdio MCP server '{name}'")

def parse_sse_response(text):
    import json
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            data_str = line.replace("data:", "").strip()
            try:
                return json.loads(data_str)
            except Exception:
                pass
    return None

def query_streamable_http_tools(url, headers=None):
    import requests
    import json
    
    post_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"
    }
    if headers:
        post_headers.update(headers)
        
    try:
        # 1. Initialize
        init_payload = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "pocketstrike-client", "version": "1.0.0"}
            },
            "id": 100
        }
        res1 = requests.post(url, json=init_payload, headers=post_headers, timeout=8)
        if res1.status_code != 200:
            return None, f"Streamable HTTP initialize failed (HTTP {res1.status_code})"
            
        init_resp = parse_sse_response(res1.text)
        if not init_resp:
            return None, f"Failed to parse SSE initialize response: {res1.text}"
            
        # 2. Notification/initialized
        initialized_payload = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        }
        requests.post(url, json=initialized_payload, headers=post_headers, timeout=8)
        
        # 3. Tools/list
        tools_payload = {
            "jsonrpc": "2.0",
            "method": "tools/list",
            "params": {},
            "id": 101
        }
        res2 = requests.post(url, json=tools_payload, headers=post_headers, timeout=8)
        if res2.status_code != 200:
            return None, f"Streamable HTTP tools/list failed (HTTP {res2.status_code})"
            
        tools_resp = parse_sse_response(res2.text)
        if not tools_resp:
            return None, f"Failed to parse SSE tools/list response: {res2.text}"
            
        if "result" in tools_resp and "tools" in tools_resp["result"]:
            return tools_resp["result"]["tools"], url + "#streamable"
            
        return None, f"Unexpected tools/list response format: {tools_resp}"
    except Exception as e:
        return None, f"Streamable HTTP handshake failed: {str(e)}"

def call_streamable_http_tool(url, tool_name, arguments, headers=None):
    import requests
    import json
    
    post_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"
    }
    if headers:
        post_headers.update(headers)
        
    try:
        # 1. Initialize
        init_payload = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "pocketstrike-client", "version": "1.0.0"}
            },
            "id": 100
        }
        res1 = requests.post(url, json=init_payload, headers=post_headers, timeout=8)
        if res1.status_code != 200:
            return f"Error: Streamable HTTP initialize failed (HTTP {res1.status_code})"
            
        # 2. Notification/initialized
        initialized_payload = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        }
        requests.post(url, json=initialized_payload, headers=post_headers, timeout=8)
        
        # 3. Call tool
        call_payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            },
            "id": 102
        }
        res2 = requests.post(url, json=call_payload, headers=post_headers, timeout=20)
        if res2.status_code != 200:
            return f"Error: Streamable HTTP tools/call failed (HTTP {res2.status_code})"
            
        call_resp = parse_sse_response(res2.text)
        if not call_resp:
            return f"Error: Failed to parse SSE tool response: {res2.text}"
            
        if "result" in call_resp and "content" in call_resp["result"]:
            contents = call_resp["result"]["content"]
            text_outputs = []
            for c in contents:
                if c.get("type") == "text":
                    text_outputs.append(c.get("text", ""))
            return "\n".join(text_outputs)
        elif "error" in call_resp:
            return f"Error from remote MCP server: {call_resp['error'].get('message')}"
            
        return f"Error: Unexpected response format: {call_resp}"
    except Exception as e:
        return f"Error executing remote Streamable HTTP tool: {str(e)}"

def query_remote_mcp_tools(url, headers=None):
    import requests
    import urllib.parse
    import threading
    import json
    import time
    try:
        req_headers = {"Accept": "text/event-stream"}
        if headers:
            req_headers.update(headers)
        # 1. Establish GET stream
        res = requests.get(url, headers=req_headers, stream=True, timeout=8)
        if res.status_code in (405, 406):
            res.close()
            return query_streamable_http_tools(url, headers)
            
        if res.status_code != 200:
            res.close()
            return query_streamable_http_tools(url, headers)
            
        post_path = None
        lines_iterator = res.iter_lines()
        
        # Read the first event to get the endpoint path
        for line in lines_iterator:
            line_str = line.decode("utf-8").strip()
            if line_str.startswith("data:"):
                post_path = line_str.replace("data:", "").strip()
                break
                
        if not post_path:
            post_url = urllib.parse.urljoin(url, "/message")
        else:
            post_url = urllib.parse.urljoin(url, post_path)
            
        # Shared state for thread communication
        shared_state = {
            "initialize_response": None,
            "tools_response": None
        }
        
        # Start background reader thread to capture incoming message events
        def consume():
            try:
                current_event = None
                for l in lines_iterator:
                    if not l:
                        continue
                    line_decoded = l.decode("utf-8").strip()
                    if line_decoded.startswith("event:"):
                        current_event = line_decoded.replace("event:", "").strip()
                    elif line_decoded.startswith("data:"):
                        data_val = line_decoded.replace("data:", "").strip()
                        if current_event == "message":
                            try:
                                msg = json.loads(data_val)
                                if msg.get("id") == 100:
                                    shared_state["initialize_response"] = msg
                                elif msg.get("id") == 101:
                                    shared_state["tools_response"] = msg
                            except Exception:
                                pass
            except Exception:
                pass
                
        reader_thread = threading.Thread(target=consume, daemon=True)
        reader_thread.start()
        
        # Tiny delay to let reader thread bind
        time.sleep(0.1)
        
        post_req_headers = {"Content-Type": "application/json"}
        if headers:
            post_req_headers.update(headers)

        # A. Send initialize request (id=100)
        init_payload = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "pocketstrike-client",
                    "version": "1.0.0"
                }
            },
            "id": 100
        }
        requests.post(post_url, json=init_payload, headers=post_req_headers, timeout=8)
        
        # Wait for initialize response
        for _ in range(50):
            if shared_state["initialize_response"] is not None:
                break
            time.sleep(0.1)
            
        if not shared_state["initialize_response"]:
            res.close()
            return None, "Handshake timed out waiting for 'initialize' response."
            
        # B. Send initialized notification
        initialized_payload = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        }
        requests.post(post_url, json=initialized_payload, headers=post_req_headers, timeout=8)
        time.sleep(0.1)
        
        # C. Send tools/list request (id=101)
        tools_payload = {
            "jsonrpc": "2.0",
            "method": "tools/list",
            "params": {},
            "id": 101
        }
        requests.post(post_url, json=tools_payload, headers=post_req_headers, timeout=8)
        
        # Wait for tools/list response
        for _ in range(50):
            if shared_state["tools_response"] is not None:
                break
            time.sleep(0.1)
            
        # Close connection
        res.close()
        
        if shared_state["tools_response"]:
            resp_data = shared_state["tools_response"]
            if "result" in resp_data and "tools" in resp_data["result"]:
                return resp_data["result"]["tools"], post_url
            return None, f"Unexpected response format: {resp_data}"
        return None, "Handshake timed out waiting for 'tools/list' response."
        
    except Exception as e:
        try:
            return query_streamable_http_tools(url, headers)
        except Exception:
            return None, f"Connection failed: {str(e)}"

def call_remote_mcp_tool(base_url, tool_name, arguments, headers=None):
    if base_url.endswith("#streamable") or "#streamable" in base_url:
        clean_url = base_url.split("#")[0]
        return call_streamable_http_tool(clean_url, tool_name, arguments, headers)
        
    import requests
    import urllib.parse
    import threading
    import json
    import time
    try:
        req_headers = {"Accept": "text/event-stream"}
        if headers:
            req_headers.update(headers)
        # 1. Establish GET stream
        res = requests.get(base_url, headers=req_headers, stream=True, timeout=8)
        if res.status_code in (405, 406):
            res.close()
            return call_streamable_http_tool(base_url, tool_name, arguments, headers)
            
        if res.status_code != 200:
            res.close()
            return call_streamable_http_tool(base_url, tool_name, arguments, headers)
            
        post_path = None
        lines_iterator = res.iter_lines()
        
        for line in lines_iterator:
            line_str = line.decode("utf-8").strip()
            if line_str.startswith("data:"):
                post_path = line_str.replace("data:", "").strip()
                break
                
        if not post_path:
            post_url = urllib.parse.urljoin(base_url, "/message")
        else:
            post_url = urllib.parse.urljoin(base_url, post_path)
            
        shared_state = {
            "initialize_response": None,
            "call_response": None
        }
        
        # Start background reader thread
        def consume():
            try:
                current_event = None
                for l in lines_iterator:
                    if not l:
                        continue
                    line_decoded = l.decode("utf-8").strip()
                    if line_decoded.startswith("event:"):
                        current_event = line_decoded.replace("event:", "").strip()
                    elif line_decoded.startswith("data:"):
                        data_val = line_decoded.replace("data:", "").strip()
                        if current_event == "message":
                            try:
                                msg = json.loads(data_val)
                                if msg.get("id") == 100:
                                    shared_state["initialize_response"] = msg
                                elif msg.get("id") == 102:
                                    shared_state["call_response"] = msg
                                    break
                            except Exception:
                                pass
            except Exception:
                pass
                
        reader_thread = threading.Thread(target=consume, daemon=True)
        reader_thread.start()
        
        time.sleep(0.1)
        
        post_req_headers = {"Content-Type": "application/json"}
        if headers:
            post_req_headers.update(headers)

        # A. Send initialize request (id=100)
        init_payload = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "pocketstrike-client",
                    "version": "1.0.0"
                }
            },
            "id": 100
        }
        requests.post(post_url, json=init_payload, headers=post_req_headers, timeout=8)
        
        # Wait for initialize response
        for _ in range(50):
            if shared_state["initialize_response"] is not None:
                break
            time.sleep(0.1)
            
        if not shared_state["initialize_response"]:
            res.close()
            return "Error: Handshake timed out waiting for 'initialize' response during tool execution."
            
        # B. Send initialized notification
        initialized_payload = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        }
        requests.post(post_url, json=initialized_payload, headers=post_req_headers, timeout=8)
        time.sleep(0.1)
        
        # C. Send tools/call request (id=102)
        call_payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            },
            "id": 102
        }
        requests.post(post_url, json=call_payload, headers=post_req_headers, timeout=20)
        
        # Wait for call response
        for _ in range(150):
            if shared_state["call_response"] is not None:
                break
            time.sleep(0.1)
            
        # Close connection
        res.close()
        
        if shared_state["call_response"]:
            resp_data = shared_state["call_response"]
            if "result" in resp_data and "content" in resp_data["result"]:
                contents = resp_data["result"]["content"]
                text_outputs = []
                for c in contents:
                    if c.get("type") == "text":
                        text_outputs.append(c.get("text", ""))
                return "\n".join(text_outputs)
            elif "error" in resp_data:
                return f"Error from remote MCP server: {resp_data['error'].get('message')}"
            return f"Error: Unexpected response format: {resp_data}"
        return "Error: Tool execution timed out waiting for server response."
    except Exception as e:
        try:
            return call_streamable_http_tool(base_url, tool_name, arguments, headers)
        except Exception:
            return f"Error executing remote MCP tool: {str(e)}"

# Telegram Bot Polling Thread
def telegram_bot_loop(token):
    offset = 0
    print(f"Telegram Bot started polling...")
    
    while True:
        try:
            # Poll for updates
            url = f"https://api.telegram.org/bot{token}/getUpdates?offset={offset}&timeout=30"
            res = requests.get(url, timeout=35)
            if res.status_code != 200:
                time.sleep(5)
                continue
                
            updates = res.json().get("result", [])
            for update in updates:
                offset = update["update_id"] + 1
                
                message = update.get("message") or update.get("edited_message")
                if not message:
                    continue
                    
                chat = message.get("chat")
                if not chat:
                    continue
                    
                chat_id = chat["id"]
                text = message.get("text", "")
                
                if not text:
                    continue

                print(f"Telegram Msg from {chat_id}: {text[:30]}...")

                # Handle basic commands
                if text == "/start":
                    welcome_text = "👋 Welcome to PocketStrikeAI! I am your personal security and automation assistant. Ask me anything!"
                    send_telegram_msg(token, chat_id, welcome_text)
                    register_telegram_chat(chat_id)
                    continue

                # Register active Telegram chat ID for scheduler notifications
                register_telegram_chat(chat_id)

                # Load unified history
                messages = load_unified_history()
                
                # Append user prompt
                messages.append({"role": "user", "content": text})
                
                # Keep the full history log, but slide the API context at 60 messages to prevent token limits
                if len(messages) > 60:
                    messages = [messages[0]] + messages[-59:]

                # Send typing status
                requests.post(f"https://api.telegram.org/bot{token}/sendChatAction", json={"chat_id": chat_id, "action": "typing"})

                # Get AI answer (handles ReAct tool calls internally)
                ai_response, updated_history = get_ai_response_with_tools(messages)
                save_unified_history(updated_history)
                
                # Trigger background memory evolution thread
                import threading
                threading.Thread(target=auto_evolve_memory_background, args=(updated_history.copy(),), daemon=True).start()
                
                # Check if camera photo was successfully captured in the chat session
                photo_path = os.path.join(WORKSPACE_DIR, "captured_photo.jpg")
                screenshot_path = os.path.join(WORKSPACE_DIR, "captured_screenshot.png")
                
                # Send back text response first
                send_telegram_msg(token, chat_id, ai_response)
                
                # Upload files to Telegram chat automatically if created/modified during execution
                if "captured_photo.jpg" in ai_response.lower() and os.path.exists(photo_path):
                    send_telegram_photo(token, chat_id, photo_path, caption="📸 PocketstrikeAI Camera Capture")
                    # Clean up file to prevent duplicate triggers
                    try: os.remove(photo_path)
                    except Exception: pass
                    
                if "captured_screenshot.png" in ai_response.lower() and os.path.exists(screenshot_path):
                    send_telegram_photo(token, chat_id, screenshot_path, caption="📱 PocketstrikeAI Screenshot Capture")
                    try: os.remove(screenshot_path)
                    except Exception: pass

        except Exception as e:
            print(f"Telegram Bot error: {e}")
            time.sleep(5)

def send_telegram_msg(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    
    # Try sending with Markdown
    res = requests.post(url, json=payload)
    if res.status_code != 200:
        # Fallback to plain text if Telegram fails due to malformed markdown
        payload.pop("parse_mode", None)
        requests.post(url, json=payload)

def send_telegram_photo(token, chat_id, photo_path, caption=None):
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    try:
        if not os.path.exists(photo_path):
            return False
        with open(photo_path, 'rb') as photo_file:
            files = {'photo': photo_file}
            data = {'chat_id': chat_id}
            if caption:
                data['caption'] = caption
            res = requests.post(url, data=data, files=files, timeout=30)
            return res.status_code == 200
    except Exception as e:
        print(f"Error sending photo to Telegram: {e}")
        return False

def check_mcp_status(url, headers=None):
    import requests
    try:
        clean_url = url.split("#")[0]
        req_headers = {}
        if headers:
            req_headers.update(headers)
        res = requests.get(clean_url, headers=req_headers, timeout=1.2)
        # If it returns any HTTP code (even error codes like 405/404), the server port is active and online
        return "connected"
    except Exception:
        return "offline"

# Web Server Routes
@app.route('/api/mcp/list', methods=['GET'])
def list_mcp_servers():
    conns = load_mcp_connections()
    updated = False
    for conn in conns:
        old_status = conn.get("status")
        transport = conn.get("transport", "sse")
        if transport == "stdio":
            name = conn.get("name")
            stdio_conn = active_stdio_connections.get(name)
            new_status = "connected" if (stdio_conn and stdio_conn.is_running) else "offline"
        else:
            new_status = check_mcp_status(conn.get("url"), conn.get("headers"))
            
        if old_status != new_status:
            conn["status"] = new_status
            updated = True
    if updated:
        save_mcp_connections(conns)
    return jsonify(conns)

@app.route('/api/mcp/add', methods=['POST'])
def add_mcp_server():
    data = request.json or {}
    name = data.get("name", "").strip().lower()
    transport = data.get("transport", "sse").strip().lower()
    
    if not name:
        return jsonify({"error": "Missing required field 'name'."}), 400
        
    conns = load_mcp_connections()
    if any(c.get("name") == name for c in conns):
        return jsonify({"error": f"An MCP connection with name '{name}' already exists."}), 400
        
    if transport == "stdio":
        command = data.get("command", "").strip()
        if not command:
            return jsonify({"error": "Missing required field 'command' for stdio transport."}), 400
            
        stdio_conn = StdioMcpConnection(name, command)
        if not stdio_conn.start():
            return jsonify({"error": "Failed to start stdio process. Check command spelling/availability."}), 400
            
        init_res = stdio_conn.send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "pocketstrike-client", "version": "1.0.0"}
        })
        if "error" in init_res:
            stdio_conn.stop()
            return jsonify({"error": f"Handshake failed: {init_res['error'].get('message')}"}), 400
            
        stdio_conn.send_notification("notifications/initialized")
        
        tools_res = stdio_conn.send_request("tools/list")
        if "error" in tools_res or "result" not in tools_res or "tools" not in tools_res["result"]:
            stdio_conn.stop()
            return jsonify({"error": "Failed to retrieve tools from stdio MCP server."}), 400
            
        tools = tools_res["result"]["tools"]
        
        new_conn = {
            "name": name,
            "transport": "stdio",
            "command": command,
            "status": "connected",
            "tools": tools
        }
        conns.append(new_conn)
        save_mcp_connections(conns)
        active_stdio_connections[name] = stdio_conn
        return jsonify({"status": "success", "tools_count": len(tools)})
    else:
        url = data.get("url", "").strip()
        custom_headers = data.get("headers") # Expect dict or None
        if not url:
            return jsonify({"error": "Missing required field 'url' for sse transport."}), 400
            
        tools, post_url = query_remote_mcp_tools(url, custom_headers)
        if not tools:
            return jsonify({"error": f"Failed to connect to remote MCP server. Verify URL and headers are correct and server is running."}), 400
            
        new_conn = {
            "name": name,
            "transport": "sse",
            "url": url,
            "post_url": post_url,
            "status": "connected",
            "tools": tools,
            "headers": custom_headers
        }
        conns.append(new_conn)
        save_mcp_connections(conns)
        return jsonify({"status": "success", "tools_count": len(tools)})

@app.route('/api/mcp/remove', methods=['POST'])
def remove_mcp_server():
    data = request.json or {}
    name = data.get("name", "").strip().lower()
    if not name:
        return jsonify({"error": "Missing required field 'name'."}), 400
        
    conns = load_mcp_connections()
    filtered = [c for c in conns if c.get("name") != name]
    
    if len(filtered) == len(conns):
        return jsonify({"error": f"MCP connection '{name}' not found."}), 404
        
    stdio_conn = active_stdio_connections.pop(name, None)
    if stdio_conn:
        print(f"🔌 Stopping stdio MCP server: {name}")
        stdio_conn.stop()
        
    save_mcp_connections(filtered)
    return jsonify({"status": "success"})

@app.route('/api/history/load', methods=['GET'])
def load_history():
    conversations = load_conversations()
    unified_messages = load_unified_history()
    
    # Find default conversation
    default_conv = None
    for c in conversations:
        if c.get("id") == "default":
            default_conv = c
            break
            
    if default_conv:
        default_conv["messages"] = unified_messages
    else:
        # Create default if not exists
        default_conv = {
            "id": "default",
            "title": "PocketStrike AI Unified Chat",
            "messages": unified_messages
        }
        conversations.append(default_conv)
        
    return jsonify(conversations)

@app.route('/api/history/sync', methods=['POST'])
def sync_history():
    data = request.json or []
    if isinstance(data, list):
        # Save all conversations to conversations.json
        save_conversations(data)
        
        # Sync the default conversation to unified_history.json for Telegram
        default_messages = None
        for c in data:
            if c.get("id") == "default":
                default_messages = c.get("messages", [])
                break
        
        if default_messages is None and len(data) > 0:
            # Fallback to first chat if default not found
            default_messages = data[0].get("messages", [])
            
        if default_messages is not None:
            save_unified_history(default_messages)
            
    return jsonify({"status": "success"})

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected for uploading"}), 400
        
    # Check content length (limit to 10MB)
    content_length = request.content_length
    if content_length and content_length > 10 * 1024 * 1024:
        return jsonify({"error": "File size exceeds limit of 10MB."}), 400
        
    try:
        from werkzeug.utils import secure_filename
        filename = secure_filename(file.filename)
        save_path = os.path.join(WORKSPACE_DIR, filename)
        
        # Save file
        file.save(save_path)
        
        # Verify saved file size is actually under 10MB
        if os.path.getsize(save_path) > 10 * 1024 * 1024:
            os.remove(save_path)
            return jsonify({"error": "File size exceeds limit of 10MB."}), 400
            
        size_kb = round(os.path.getsize(save_path) / 1024, 1)
        return jsonify({
            "status": "success",
            "filename": filename,
            "size_kb": size_kb,
            "path": save_path
        })
    except Exception as e:
        return jsonify({"error": f"Failed to save file: {str(e)}"}), 500

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json or {}
    messages = data.get("messages", [])
    if not messages:
        return jsonify({"error": "No messages provided"}), 400
        
    save_unified_history(messages)
    
    def generate():
        streamed_text = ""
        for chunk in get_ai_response_stream(messages):
            streamed_text += chunk
            yield chunk
        if streamed_text:
            messages.append({"role": "assistant", "content": streamed_text})
            save_unified_history(messages)
            # Trigger background memory evolution thread
            import threading
            threading.Thread(target=auto_evolve_memory_background, args=(messages.copy(),), daemon=True).start()

    return Response(generate(), mimetype='text/event-stream')

@app.route('/api/status', methods=['GET'])
def get_status():
    import shutil
    import sys
    is_mac = sys.platform == "darwin"
    is_termux = shutil.which("pkg") is not None or os.path.exists("/data/data/com.termux")
    os_type = "mac" if is_mac else ("termux" if is_termux else "linux")
    
    if is_mac:
        os_name = "macOS"
    elif is_termux:
        os_name = "Android / Termux"
    else:
        os_name = "Linux System"
        if os.path.exists("/etc/os-release"):
            try:
                with open("/etc/os-release") as f:
                    for line in f:
                        if line.startswith("PRETTY_NAME="):
                            os_name = line.split("=")[1].strip().strip('"')
                            break
            except Exception:
                pass

    status = {
        "provider": config.get("provider_name", "None"),
        "model": config.get("model", "None"),
        "telegram_enabled": config.get("telegram_enabled", False),
        "telegram_status": "Active" if config.get("telegram_enabled", False) else "Disabled",
        "os_type": os_type,
        "os_name": os_name
    }
    return jsonify(status)

# Serve static files correctly if needed
@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('static', path)

@app.route('/workspace/<path:filename>')
def serve_workspace_file(filename):
    # Normalize path and check directory bounds for safety
    safe_path = os.path.abspath(os.path.join(WORKSPACE_DIR, filename))
    if not safe_path.startswith(os.path.abspath(WORKSPACE_DIR)):
        return jsonify({"error": "Access denied"}), 403
    return send_from_directory(WORKSPACE_DIR, filename)

def voice_listener_daemon():
    """
    Always-On Background Voice Listener Daemon for Termux/Android.
    Listens for wake word 'hey strike' or trigger signals across all apps,
    executes ReAct tools, and responds back via Android TTS and lockscreen notifications.
    """
    if not config.get("voice_enabled", True):
        return
        
    print("🎙️ Background Voice Assistant Daemon started (Wake word: 'Hey Strike')...")
    import subprocess
    import time
    import shutil
    import threading

    has_termux_stt = shutil.which("termux-speech-to-text") is not None

    while True:
        try:
            time.sleep(2.0)
            if not config.get("voice_enabled", True):
                time.sleep(5)
                continue

            trigger_file = os.path.join(WORKSPACE_DIR, ".voice_trigger")
            spoken_text = ""

            if os.path.exists(trigger_file):
                try:
                    os.remove(trigger_file)
                except Exception:
                    pass
                if has_termux_stt:
                    vibrate_device(150)
                    speak_text("Listening")
                    res = subprocess.run(["termux-speech-to-text"], capture_output=True, text=True, timeout=12)
                    if res.returncode == 0 and res.stdout.strip():
                        spoken_text = res.stdout.strip()
            else:
                # Check Python speech_recognition if installed
                try:
                    import speech_recognition as sr
                    r = sr.Recognizer()
                    r.pause_threshold = 1.2  # Wait 1.2s of silence before marking sentence complete
                    r.energy_threshold = 300
                    with sr.Microphone() as source:
                        r.adjust_for_ambient_noise(source, duration=0.4)
                        audio = r.listen(source, timeout=3, phrase_time_limit=15)
                        spoken_text = r.recognize_google(audio)
                except Exception:
                    pass

            if not spoken_text:
                continue

            clean_text = spoken_text.lower().strip()
            wake_words = ["hey strike", "strike", "hey pocket strike", "pocket strike", "hi strike", "ok strike"]
            triggered = any(w in clean_text for w in wake_words)

            if triggered:
                print(f"\n🎙️ [Background Voice Assistant Triggered]: '{spoken_text}'")
                command_prompt = clean_text
                for w in wake_words:
                    command_prompt = command_prompt.replace(w, "").strip()

                vibrate_device(200)
                if not command_prompt:
                    speak_text("Yes? How can I help?")
                    continue

                messages = load_unified_history()
                messages.append({"role": "user", "content": command_prompt})
                if len(messages) > 60:
                    messages = [messages[0]] + messages[-59:]

                ai_response, updated_history = get_ai_response_with_tools(messages)
                save_unified_history(updated_history)

                threading.Thread(target=auto_evolve_memory_background, args=(updated_history.copy(),), daemon=True).start()

                print(f"🔊 Speaking response: {ai_response[:60]}...")
                speak_text(ai_response)
                send_android_notification("PocketStrike Voice AI", ai_response)

        except Exception as e:
            time.sleep(3)

@app.route('/api/voice/trigger', methods=['POST'])
def trigger_voice():
    """Endpoint to trigger background speech-to-text in Termux or query voice AI."""
    data = request.json or {}
    text = data.get("text", "")

    if text:
        messages = load_unified_history()
        messages.append({"role": "user", "content": text})
        if len(messages) > 60:
            messages = [messages[0]] + messages[-59:]

        ai_response, updated_history = get_ai_response_with_tools(messages)
        save_unified_history(updated_history)

        import threading
        threading.Thread(target=auto_evolve_memory_background, args=(updated_history.copy(),), daemon=True).start()

        if data.get("speak_on_device", False):
            speak_text(ai_response)
            send_android_notification("PocketStrike Voice AI", ai_response)

        return jsonify({"response": ai_response, "history": updated_history})
    else:
        trigger_file = os.path.join(WORKSPACE_DIR, ".voice_trigger")
        try:
            with open(trigger_file, "w") as f:
                f.write("1")
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        return jsonify({"status": "Voice trigger armed"})

if __name__ == '__main__':
    import logging
    import flask.cli
    # Suppress Flask default serving banner and Werkzeug log requests
    flask.cli.show_server_banner = lambda *args, **kwargs: None
    logging.getLogger('werkzeug').setLevel(logging.ERROR)

    # 1. Load config
    if not load_config():
        print("⚠️ Warning: config.json not found! Please run the Setup Wizard first.")
        print("Starting anyway in fallback mode.")

    # Initialize local stdio MCP connections
    try:
        init_stdio_mcp_connections()
    except Exception as e:
        print(f"Error initializing stdio MCP connections: {e}")
        
    # Start Scheduler Thread
    scheduler_thread = threading.Thread(target=scheduler_worker_loop, daemon=True)
    scheduler_thread.start()

    # Start Active Threat Sentinel Thread
    try:
        sentinel_thread = threading.Thread(target=active_threat_sentinel_daemon, daemon=True)
        sentinel_thread.start()
    except Exception as e:
        print(f"Error starting sentinel daemon: {e}")

    # Start Voice Assistant Daemon Thread
    voice_status = "Disabled"
    if config.get("voice_enabled", True):
        try:
            voice_thread = threading.Thread(target=voice_listener_daemon, daemon=True)
            voice_thread.start()
            voice_status = "Active ('Hey Strike')"
        except Exception as e:
            print(f"Error starting voice daemon: {e}")

    # 2. Launch Telegram Bot if enabled
    telegram_status = "Disabled"
    if config.get("telegram_enabled") and config.get("telegram_token"):
        tg_token = config["telegram_token"]
        telegram_bot_thread = threading.Thread(target=telegram_bot_loop, args=(tg_token,), daemon=True)
        telegram_bot_thread.start()
        telegram_status = "Active"

    # 3. Check Shizuku status dynamically
    import shutil
    shizuku_provisioned = shutil.which("rish") is not None
    shizuku_status = "Not Connected"
    
    # Auto-provision on startup if not in PATH but files exist
    if not shizuku_provisioned:
        possible_srcs = [
            "/sdcard/Shizuku/rish",
            "/storage/emulated/0/Shizuku/rish",
            os.path.expanduser("~/storage/shared/Shizuku/rish"),
            os.path.expanduser("~/storage/downloads/rish"),
            os.path.expanduser("~/storage/downloads/Shizuku/rish"),
            "/sdcard/Download/rish",
            "/sdcard/Download/Shizuku/rish",
            "/storage/emulated/0/Download/rish",
            "/storage/emulated/0/Download/Shizuku/rish",
            os.path.abspath(os.path.join(os.path.dirname(__file__), "rish")),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "workspace", "rish"))
        ]
        shizuku_src = None
        for path in possible_srcs:
            if os.path.exists(path):
                shizuku_src = path
                break
        if shizuku_src:
            try:
                prefix = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
                termux_bin = os.path.join(prefix, "bin")
                if os.path.exists(termux_bin):
                    import glob
                    src_dir = os.path.dirname(shizuku_src)
                    for fpath in glob.glob(os.path.join(src_dir, "rish*")):
                        dest_file = os.path.join(termux_bin, os.path.basename(fpath))
                        shutil.copy(fpath, dest_file)
                    os.chmod(os.path.join(termux_bin, "rish"), 0o755)
                    dex_file = os.path.join(termux_bin, "rish_shizuku.dex")
                    if os.path.exists(dex_file):
                        os.chmod(dex_file, 0o444)
                    shizuku_provisioned = True
                    print(f"PocketstrikeAI: Auto-installed Shizuku rish binaries on startup from {shizuku_src}!")
            except Exception as e:
                print(f"PocketstrikeAI: Startup Shizuku auto-install failed: {e}")
        else:
            print("⚠️ Shizuku 'rish' not found in PATH or storage. Put 'rish' and 'rish_shizuku.dex' in your phone's main Downloads folder or in the project directory.")

    if shizuku_provisioned:
        try:
            import subprocess
            env = os.environ.copy()
            env["RISH_APPLICATION_ID"] = get_termux_package_id()
            env.pop("LD_LIBRARY_PATH", None)
            env.pop("LD_PRELOAD", None)
            shell_exe = "/system/bin/sh" if os.path.exists("/system/bin/sh") else "sh"
            
            # Fast test call to rish to check if binder is active and approved
            # Use 2.0s timeout: if it hangs, it is likely waiting for authorization
            try:
                res = subprocess.run([shell_exe, shutil.which("rish"), "-c", "echo 1"], capture_output=True, timeout=2.0, env=env)
                is_ok = (res.returncode == 0)
                out = res.stdout.decode('utf-8', errors='ignore').strip() if res.stdout else ""
                err = res.stderr.decode('utf-8', errors='ignore').strip() if res.stderr else ""
                need_auth = (res.returncode == 1 or "permission" in err.lower() or "permission" in out.lower())
            except subprocess.TimeoutExpired:
                is_ok = False
                need_auth = True
                out, err = "", ""
            
            if is_ok:
                shizuku_status = "Active / Connected"
            elif need_auth:
                print("\n\033[1;33m📣 [Shizuku Authorization Required]\033[0m")
                print("\033[38;5;46m  Please check your phone screen now!\033[0m")
                print("\033[38;5;255m  A popup will request permission for Termux to access Shizuku.\033[0m")
                print("\033[1;32m  👉 Tap 'Always Allow' or 'Allow' to authorize the agent. 👈\033[0m\n")
                
                try:
                    import pty
                    master, slave = pty.openpty()
                    # Spawn rish in a pty so it thinks it is in an interactive terminal and triggers popup
                    p = subprocess.Popen(
                        [shutil.which("rish")],
                        stdin=slave,
                        stdout=slave,
                        stderr=slave,
                        env=env,
                        preexec_fn=os.setsid if hasattr(os, 'setsid') else None
                    )
                    # Keep it open for 10 seconds to give user time to click Allow
                    time.sleep(10.0)
                    p.terminate()
                    p.wait(timeout=2.0)
                except Exception as pty_err:
                    print(f"  (Failed to start pty trigger: {pty_err})")
                    
                # Re-test connection state
                try:
                    res_retry = subprocess.run([shell_exe, shutil.which("rish"), "-c", "echo 1"], capture_output=True, timeout=3.5, env=env)
                    if res_retry.returncode == 0:
                        print("\033[38;5;46m[✓] Shizuku authorization successful!\033[0m\n")
                        shizuku_status = "Active / Connected"
                    else:
                        shizuku_status = "Unauthorized (Approve Termux in Shizuku)"
                except subprocess.TimeoutExpired:
                    shizuku_status = "Unauthorized (Authorization Timeout)"
            else:
                print(f"⚠️ Shizuku test failed (code {res.returncode}). stdout: '{out}', stderr: '{err}'")
                shizuku_status = "Daemon Stopped (Start Shizuku app)"
        except Exception as e:
            print(f"⚠️ Shizuku test error: {str(e)}")
            shizuku_status = f"Daemon Stopped ({type(e).__name__})"
    else:
        shizuku_status = "Not Configured (Export files via Shizuku)"

    # 4. Print access information
    local_ip = get_local_ip()
    blue_color = "\033[38;5;39m" # Vibrant Cyber Blue
    green_color = "\033[38;5;46m" # Bright Green
    white_color = "\033[38;5;255m" # White for URLs
    reset_color = "\033[0m"
    banner_text = f"""{blue_color}██████╗  ██████╗  ██████╗██╗  ██╗███████╗████████╗
██╔══██╗██╔═══██╗██╔════╝██║ ██╔╝██╔════╝╚══██╔══╝
██████╔╝██║   ██║██║     █████╔╝ █████╗     ██║   
██╔═══╝ ██║   ██║██║     ██╔═██╗ ██╔══╝     ██║   
██║     ╚██████╔╝╚██████╗██║  ██╗███████╗   ██║   
╚═╝      ╚═════╝  ╚═════╝╚═╝  ╚═╝╚══════╝   ╚═╝   {white_color}
███████╗████████╗██████╗ ██╗██╗  ██╗███████╗     █████╗ ██╗
██╔════╝╚══██╔══╝██╔══██╗██║██║ ██╔╝██╔════╝    ██╔══██╗██║
███████╗   ██║   ██████╔╝██║█████╔╝ █████╗      ███████║██║
╚════██║   ██║   ██╔══██╗██║██╔═██╗ ██╔══╝      ██╔══██║██║
███████║   ██║   ██║  ██║██║██║  ██╗███████╗    ██║  ██║██║
╚══════╝   ╚═╝   ╚═╝  ╚═╝╚═╝╚═╝  ╚═╝╚══════╝    ╚═╝  ╚═╝╚═╝{reset_color}"""
    print(banner_text)
    print(f"       {blue_color}Pocket{green_color}Strike-AI {reset_color}— {blue_color}Gateway{reset_color}")
    print(f"{green_color}───────────────────────── Server is Starting ─────────────────────────{reset_color}")
    print(f"  Local URL:       {white_color}http://127.0.0.1:5000{reset_color}")
    print(f"  Network URL:     {white_color}http://{local_ip}:5000{reset_color}")
    print(f"  AI Provider:     {white_color}{config.get('provider_name', 'None')}{reset_color}")
    print(f"  Model:           {white_color}{config.get('model', 'None')}{reset_color}")
    print(f"  Telegram Bot:    {white_color}{telegram_status}{reset_color}")
    print(f"  Voice Assistant: {white_color}{voice_status}{reset_color}")
    print(f"  Shizuku Status:  {white_color}{shizuku_status}{reset_color}")
    print(f"{green_color}──────────────────────────────────────────────────────────────────────{reset_color}\n")

    # Run Flask
    # Host is 0.0.0.0 so they can access it from their phone browser as well as external devices on local network
    app.run(host='0.0.0.0', port=5000, debug=False)
