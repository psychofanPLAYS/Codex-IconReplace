on run
	set appPath to POSIX path of (path to me)
	set shellCmd to "APP_PATH=" & quoted form of appPath & "
APP_DIR=\"$(cd \"$(dirname \"$APP_PATH\")\" && pwd)\"
cd \"$APP_DIR\"
xattr -d com.apple.quarantine \"scripts/replace-chatgpt-icons.sh\" 2>/dev/null || true
chmod +x \"scripts/replace-chatgpt-icons.sh\"
\"$APP_DIR/scripts/replace-chatgpt-icons.sh\"
"
	try
		do shell script shellCmd
		display notification "Codex icon successfully updated!" with title "Codex Icon Updater"
		display dialog "Codex icon successfully updated!" buttons {"OK"} default button "OK" with title "Codex Icon Updater"
	on error errMsg number errNum
		display dialog "Error updating Codex icon: " & errMsg buttons {"OK"} default button "OK" with icon stop with title "Codex Icon Updater"
	end try
end run
