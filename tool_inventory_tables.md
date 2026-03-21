## ADMIN
| Tool | Description | Destructive | Module |
|---|---|---:|---|
| admin_export_registry_key | Export a Windows registry key to a .reg file. | true | admin_toolkit.py |
| admin_generate_disk_report | Generate a simple disk usage report for a directory. | true | admin_toolkit.py |
| admin_list_startup_programs | List Windows startup programs from the registry. | true | admin_toolkit.py |
| admin_network_snapshot | Capture current network connections and listening ports. | true | admin_toolkit.py |
| admin_summarize_event_logs | Export recent Windows event logs (Application). | true | admin_toolkit.py |

## API
| Tool | Description | Destructive | Module |
|---|---|---:|---|
| api_datetime | Get the current date and time, optionally for a specific timezone. | false | api_toolkit.py |
| api_http_request | Make an HTTP request (GET or POST) to any URL and return the response. Use for generic API calls. | false | api_toolkit.py |
| api_weather | Get current weather for a latitude/longitude using Open-Meteo (free, no API key). | false | api_toolkit.py |

## ARCHIVE
| Tool | Description | Destructive | Module |
|---|---|---:|---|
| archive_create_zip | Create a ZIP archive from a file or directory on the host OS. | true | archive_image_toolkit.py |
| archive_extract_zip | Extract a ZIP archive to the host OS. | true | archive_image_toolkit.py |

## AUDIO
| Tool | Description | Destructive | Module |
|---|---|---:|---|
| audio_record_microphone | Record microphone audio to a WAV file on the host OS. | true | audio_record_toolkit.py |
| audio_text_to_speech | Convert text to speech and save as MP3 on the host OS. | true | audio_toolkit.py |

## CLIPBOARD
| Tool | Description | Destructive | Module |
|---|---|---:|---|
| clipboard_transform_text | Transform clipboard text to upper/lower/title case. | true | singularity_toolkit.py |

## COMM
| Tool | Description | Destructive | Module |
|---|---|---:|---|
| comm_send_email | Open the default email client with a pre-filled draft. | false | communication_toolkit.py |

## DATA
| Tool | Description | Destructive | Module |
|---|---|---:|---|
| data_batch_rename | Rename many files using a regex replacement pattern. | true | data_manipulation_toolkit.py |
| data_csv_profile | Profile CSV file: row count, columns, null-like counts, and preview. | false | insight_toolkit.py |
| data_excel_to_json | Convert Excel sheets into structured JSON rows. | false | data_manipulation_toolkit.py |
| data_find_duplicates | Hash files in a directory and list exact duplicates. | false | data_manipulation_toolkit.py |
| data_hash_text | Generate deterministic hash for text using md5/sha1/sha256/sha512. | false | insight_toolkit.py |
| data_merge_json | Merge multiple JSON files into a single JSON array or object list. | true | singularity_toolkit.py |
| data_query_csv_sql | Load a CSV into in-memory SQLite and query it with SQL. | false | data_manipulation_toolkit.py |
| data_validate_json | Validate JSON text and optionally assert required top-level keys. | false | insight_toolkit.py |
| data_zip_and_encrypt | Zip a directory and encrypt the archive with a password. | true | data_manipulation_toolkit.py |

## DESKTOP
| Tool | Description | Destructive | Module |
|---|---|---:|---|
| desktop_send_notification | Send a native Windows desktop notification. | true | singularity_toolkit.py |

## DEV
| Tool | Description | Destructive | Module |
|---|---|---:|---|
| dev_auto_debugger | Auto triage failing command/test and provide structured debug hints. | true | omega_directive_toolkit.py |
| dev_decode_base64 | Decode a Base64 string into text. | false | developer_extra_toolkit.py |
| dev_dependency_audit | Audit dependencies (uv pip check / pip check) and emit actionable report. | true | omega_directive_toolkit.py |
| dev_docker_manage | Run docker or docker-compose commands. | true | devops_engineering_toolkit.py |
| dev_execute_python_code | Execute Python code in a temporary file (10s timeout). | true | developer_toolkit.py |
| dev_format_json | Format a JSON string with indentation. | false | developer_extra_toolkit.py |
| dev_git_commit_push | Stage, commit, and push git changes in a target repository path. | true | devops_engineering_toolkit.py |
| dev_lint_and_format | Run black and flake8 on a file or directory. | true | devops_engineering_toolkit.py |
| dev_run_pytest_suite | Run the pytest suite and return raw logs. | true | devops_engineering_toolkit.py |
| dev_run_sqlite_query | Run a read-only SQL query against the OmniCore database. | true | developer_toolkit.py |

## DOC
| Tool | Description | Destructive | Module |
|---|---|---:|---|
| doc_pdf_to_text_advanced | Convert a PDF to text using page-aware extraction. | false | singularity_toolkit.py |
| doc_read_pdf | Extract text from a PDF or DOCX file on the host OS. | false | document_toolkit.py |

## FILE
| Tool | Description | Destructive | Module |
|---|---|---:|---|
| file_watch_directory | Snapshot a directory state and write a hash report. | false | singularity_toolkit.py |

## GUI
| Tool | Description | Destructive | Module |
|---|---|---:|---|
| gui_analyze_screen | Take a screenshot and extract visible text using Gemini vision. | true | vision_toolkit.py |
| gui_autonomous_explorer | Hybrid GUI fallback: opens target in visible browser and foregrounds it. | true | omega_directive_toolkit.py |
| gui_click_image_on_screen | Find an image on screen and click it. | true | computer_use_toolkit.py |
| gui_drag_and_drop | Drag the mouse from point A to point B. | true | computer_use_toolkit.py |
| gui_extract_text_from_region | Capture a screen region and extract text using Gemini vision. | true | computer_use_toolkit.py |
| gui_foreground_guard | Assert/force window foreground by title and verify active window text. | true | omega_directive_toolkit.py |
| gui_get_mouse_position | Return current mouse cursor coordinates. | false | gui_automation_toolkit.py |
| gui_human_type | Type text with variable human-like delays. | true | computer_use_toolkit.py |
| gui_locate_and_click | Take a screenshot, use Gemini vision to locate a described UI element, and click its center coordinates. | true | computer_use_toolkit.py |
| gui_mouse_move_click | Move the mouse to (x, y) and optionally click. | true | gui_automation_toolkit.py |
| gui_press_hotkey | Press a combination of keys (e.g., ctrl+c). | true | gui_automation_toolkit.py |
| gui_record_screen | Record the screen for N seconds and save as MP4. | true | computer_use_toolkit.py |
| gui_scroll_mouse | Scroll mouse wheel by a number of clicks. | true | gui_automation_toolkit.py |
| gui_take_screenshot | Take a screenshot of the entire screen or a region. | true | gui_automation_toolkit.py |
| gui_type_text | Type a string using the keyboard. | true | gui_automation_toolkit.py |

## IMAGE
| Tool | Description | Destructive | Module |
|---|---|---:|---|
| image_read_exif | Read EXIF metadata from an image on the host OS. | false | archive_image_toolkit.py |

## IMG
| Tool | Description | Destructive | Module |
|---|---|---:|---|
| img_read_qr_code | Read QR codes from an image using OpenCV. | false | singularity_toolkit.py |

## MEDIA
| Tool | Description | Destructive | Module |
|---|---|---:|---|
| media_contact_sheet | Build a contact sheet from images in a folder. | true | singularity_toolkit.py |
| media_control_spotify_native | Control active Spotify/media session (play, pause, next, previous). | true | advanced_os_toolkit.py |
| media_convert_video | Convert a video file to MP4 using ffmpeg. | true | media_studio_toolkit.py |
| media_download_youtube_audio | Download YouTube audio as MP3/M4A to the host OS. | true | media_toolkit.py |
| media_extract_audio | Extract audio from a video file as MP3. | true | media_studio_toolkit.py |
| media_extract_text_from_video | Extract text transcript from a local video by converting audio and applying STT. | true | media_studio_toolkit.py |
| media_generate_tts_human | Generate natural TTS audio via Edge-TTS. | true | media_studio_toolkit.py |
| media_get_youtube_transcript | Fetch the transcript for a YouTube video by URL or ID. | false | media_toolkit.py |
| media_screen_record_invisible | Start/stop stealth screen recording in background while other tools run. | true | computer_use_toolkit.py |
| media_watermark_image | Overlay watermark text onto an image. | true | media_studio_toolkit.py |

## NET
| Tool | Description | Destructive | Module |
|---|---|---:|---|
| net_connection_kill_switch | Kill connections by remote host or port using native OS commands. | true | omega_directive_toolkit.py |
| net_ftp_client | Connect to FTP and list or download files. | true | network_infrastructure_toolkit.py |
| net_get_ip | Return internal and external IP addresses. | false | network_toolkit.py |
| net_http_probe | Probe an HTTP endpoint and return status, timing, and headers. | false | singularity_toolkit.py |
| net_intercept_and_analyze | Capture a live socket snapshot and return a basic risk analysis. | false | network_infrastructure_toolkit.py |
| net_monitor_live_traffic | Run netstat -ano and show active remote IP communications. | false | network_infrastructure_toolkit.py |
| net_packet_sniffer | Capture packet summary using tshark/tcpdump/pktmon backends. | true | omega_directive_toolkit.py |
| net_ping | Ping a host and return latency output. | false | network_toolkit.py |
| net_ssh_execute | Connect to SSH and execute a command. | true | network_infrastructure_toolkit.py |
| net_start_local_server | Start a temporary local HTTP server on a given port. | true | network_infrastructure_toolkit.py |
| net_stealth_port_scan | Scan common ports on a host and report which are open. | true | network_infrastructure_toolkit.py |
| net_traceroute | Run Windows tracert against a host. | true | network_infrastructure_toolkit.py |
| net_wifi_connect | Connect to a Wi-Fi network by SSID using netsh on Windows. | true | network_infrastructure_toolkit.py |

## OS
| Tool | Description | Destructive | Module |
|---|---|---:|---|
| os_clipboard_history_manager | Manage clipboard history: read current, store to history, list recent entries, or restore a previous entry. | true | advanced_os_toolkit.py |
| os_clipboard_read | Read text from the system clipboard. | false | advanced_os_toolkit.py |
| os_clipboard_write | Write text to the system clipboard. | true | advanced_os_toolkit.py |
| os_control_audio | Get/set/mute/unmute the Windows master volume. | true | windows_power_toolkit.py |
| os_cross_root_inventory | Inventory selected roots across drives/filesystems with size and counts. | false | omega_directive_toolkit.py |
| os_deep_search | Search any drive/root for files by name with optimized native search backends. | true | network_infrastructure_toolkit.py |
| os_delete_file | Delete a file or directory on the host OS. | true | os_toolkit.py |
| os_execute_elevated | Execute a command with admin/root elevation based on host OS. | true | advanced_os_toolkit.py |
| os_get_now_playing | Get currently playing media title/artist from Windows session. | false | advanced_os_toolkit.py |
| os_kill_process | Kill a process by PID. | true | advanced_os_toolkit.py |
| os_launch_application | Launch desktop/UWP applications on Windows (e.g., Spotify, Steam). | true | advanced_os_toolkit.py |
| os_list_dir | List files and directories on the host OS. | false | os_toolkit.py |
| os_list_running_processes | List top 15 memory-consuming processes. | false | advanced_os_toolkit.py |
| os_manage_windows | Minimize all windows, restore windows, or show desktop. | true | windows_power_toolkit.py |
| os_move_file | Move or rename a file or directory on the host OS. | true | os_toolkit.py |
| os_open_browser_visible | Open a URL in the user's real default browser in a visible tab. | true | advanced_os_toolkit.py |
| os_path_inspect | Inspect host path metadata (type, size, and timestamps). | false | insight_toolkit.py |
| os_phantom_file_hider | Toggle hidden attribute on a file or directory (Windows only). | true | advanced_os_toolkit.py |
| os_read_file | Read the contents of a file on the host OS. | false | os_toolkit.py |
| os_registry_deep_tweak | Read/write/delete Windows Registry values with strict guardrails. | true | omega_directive_toolkit.py |
| os_resource_monitor | Return current CPU, RAM, and Disk usage. | false | advanced_os_toolkit.py |
| os_system_info | Report current CPU and memory usage of the host system. | false | os_toolkit.py |
| os_track_active_window | Report the currently active foreground window title. | false | singularity_toolkit.py |
| os_write_file | Write content to a file on the host OS. | true | os_toolkit.py |

## OSINT
| Tool | Description | Destructive | Module |
|---|---|---:|---|
| osint_dns_lookup | Get A, MX, TXT, and CNAME DNS records for a domain. | false | deep_web_osint_toolkit.py |

## SCHED
| Tool | Description | Destructive | Module |
|---|---|---:|---|
| sched_add_dynamic_reminder | Schedule a one-off reminder to send a Telegram message. | true | scheduler_toolkit.py |

## SEC
| Tool | Description | Destructive | Module |
|---|---|---:|---|
| sec_decrypt_file | Decrypt a file with a password (AES via Fernet). | true | security_toolkit.py |
| sec_encrypt_file | Encrypt a file with a password (AES via Fernet). | true | security_toolkit.py |

## STEG
| Tool | Description | Destructive | Module |
|---|---|---:|---|
| steg_hide_message | Hide a short message in a PNG image. | true | steganography_toolkit.py |
| steg_reveal_message | Reveal a hidden message from a PNG image. | false | steganography_toolkit.py |

## SYS
| Tool | Description | Destructive | Module |
|---|---|---:|---|
| sys_auto_troubleshooter | Collect system diagnostics and suggest likely root causes for common failures. | false | advanced_os_toolkit.py |
| sys_clean_temp_files | Clear Windows temp directories and report freed space. | true | system_optimizer_toolkit.py |
| sys_clear_browser_caches | Clear common browser cache folders (Chrome/Edge). | true | browser_cache_toolkit.py |
| sys_control_hardware | Adjust screen brightness or volume using native Windows commands. | true | system_kernel_toolkit.py |
| sys_edit_registry | Read or write values in the Windows Registry. | true | system_kernel_toolkit.py |
| sys_environment_snapshot | Capture current environment variables and key system paths. | false | singularity_toolkit.py |
| sys_find_large_files | Find top 10 largest files over a size threshold. | false | system_optimizer_toolkit.py |
| sys_flush_dns_cache | Flush Windows DNS cache using ipconfig /flushdns. | true | system_optimizer_toolkit.py |
| sys_force_foreground | Find a window by title and force it to foreground. | true | advanced_os_toolkit.py |
| sys_get_all_installed_apps | List installed apps by querying Windows Uninstall registry keys. | false | advanced_os_toolkit.py |
| sys_get_wifi_passwords | Extract saved Wi-Fi profiles and their passwords using netsh. | true | system_kernel_toolkit.py |
| sys_hardware_serials | Extract motherboard, BIOS, and disk serial numbers. | false | singularity_toolkit.py |
| sys_kill_task_forcefully | Force-kill a process by name or PID using taskkill /F on Windows. | true | system_kernel_toolkit.py |
| sys_manage_services | Start, stop, or restart a Windows service via sc.exe. | true | system_kernel_toolkit.py |
| sys_network_scanner | Ping a local subnet and report active hosts. | true | monitoring_toolkit.py |
| sys_platform_probe | Collect cross-platform runtime and shell/backend availability map. | false | omega_directive_toolkit.py |
| sys_read_notifications | Read recent Windows notifications from Event Log and app state data. | false | advanced_os_toolkit.py |
| sys_wmi_hardware_audit | Run deep hardware audit via WMI/WMIC (Windows) or platform fallback. | false | omega_directive_toolkit.py |

## TERMINAL
| Tool | Description | Destructive | Module |
|---|---|---:|---|
| terminal_execute | Execute a shell command in a host working directory. Requires explicit user approval before running. | true | terminal_toolkit.py |

## TEXT
| Tool | Description | Destructive | Module |
|---|---|---:|---|
| text_profile_basic | Compute basic text profile: lines, words, chars, and top tokens. | false | insight_toolkit.py |

## WEB
| Tool | Description | Destructive | Module |
|---|---|---:|---|
| web_bypass_cloudflare | Use undetected_chromedriver to bypass Cloudflare and fetch rendered HTML. | true | deep_web_osint_toolkit.py |
| web_bypass_scraper | Fetch HTML using browser-like headers to bypass simple blocks. | false | deep_web_osint_toolkit.py |
| web_deep_crawl | Crawl a site up to a limited depth and return page texts. | false | web_research_toolkit.py |
| web_deep_scraper | Use Playwright to navigate, dismiss cookie prompts, and extract array data. | false | workflow_toolkit.py |
| web_download_all_images | Download all images from a page to the host OS. | true | deep_web_osint_toolkit.py |
| web_download_file | Download a URL directly into the real Windows Downloads folder. | true | web_toolkit.py |
| web_execute_javascript | Execute JavaScript on a page URL and return the result. | true | web_toolkit.py |
| web_extract_all_emails | Extract all public email addresses from a web page. | false | deep_web_osint_toolkit.py |
| web_extract_all_links | Extract all hyperlinks from a URL. | false | advanced_web_toolkit.py |
| web_extract_tables | Extract HTML tables from a webpage into JSON rows. | false | singularity_toolkit.py |
| web_fetch_hackernews_top | Fetch top Hacker News stories. | false | singularity_toolkit.py |
| web_fetch_rss_feed | Fetch and summarize an RSS/Atom feed. | false | singularity_toolkit.py |
| web_monitor_changes | Fetch a URL, hash its content, and compare against previous state. | false | monitoring_toolkit.py |
| web_navigate | Navigate to a URL and return the page text content. | false | web_toolkit.py |
| web_page_to_pdf_report | Render a webpage to PDF using Playwright. | true | singularity_toolkit.py |
| web_play_youtube_video_visible | Search YouTube for a video query and open the top result in the user's real default browser. Physical browser opening is mandatory. | true | advanced_os_toolkit.py |
| web_read_main_article | Extract the main article text from a URL. | false | advanced_web_toolkit.py |
| web_screenshot | Take a screenshot of a web page and save it to the host OS. | false | web_toolkit.py |
| web_search | Search the web using DuckDuckGo and return top results. | false | web_toolkit.py |

## WORKFLOW
| Tool | Description | Destructive | Module |
|---|---|---:|---|
| workflow_set_alarm | Set a local alarm by launching Windows clock or delayed beep. | true | workflow_toolkit.py |
| workflow_system_calculator | Evaluate a math expression safely. | false | workflow_toolkit.py |
