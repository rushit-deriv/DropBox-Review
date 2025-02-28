import os
import dropbox
import json
import time

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

DROPBOX_APP_KEY = os.getenv("DROPBOX_APP_KEY")
DROPBOX_APP_SECRET = os.getenv("DROPBOX_APP_SECRET")
DROPBOX_REFRESH_TOKEN = os.getenv("DROPBOX_REFRESH_TOKEN")

def format_file_size(size_bytes):
    """Format file size in a human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"

def list_folder_contents(dbx, path="", max_items=50):
    """List folder contents with a limit on the number of items shown."""
    try:
        entries = dbx.files_list_folder(path).entries
        
        # Sort entries: folders first, then files, both alphabetically
        folders = sorted([e for e in entries if isinstance(e, dropbox.files.FolderMetadata)], key=lambda e: e.name.lower())
        files = sorted([e for e in entries if isinstance(e, dropbox.files.FileMetadata)], key=lambda e: e.name.lower())
        
        # Combine and limit
        all_entries = folders + files
        shown_entries = all_entries[:max_items]
        
        # Display entries
        for i, entry in enumerate(shown_entries):
            if isinstance(entry, dropbox.files.FolderMetadata):
                print(f"{i+1}. 📁 {entry.name}")
            else:
                size_str = format_file_size(entry.size)
                print(f"{i+1}. 📄 {entry.name} ({size_str})")
        
        # Show if there are more items
        if len(all_entries) > max_items:
            print(f"... and {len(all_entries) - max_items} more items")
        
        return folders, files
            
    except dropbox.exceptions.ApiError as err:
        print(f"Error accessing {path}: {err}")
        return [], []

def get_folder_stats(dbx, path=""):
    """Get quick statistics for the current folder."""
    try:
        entries = dbx.files_list_folder(path).entries
        
        folders = [e for e in entries if isinstance(e, dropbox.files.FolderMetadata)]
        files = [e for e in entries if isinstance(e, dropbox.files.FileMetadata)]
        
        total_size = sum(f.size for f in files)
        
        stats = {
            "folders": len(folders),
            "files": len(files),
            "total_size": total_size,
            "total_size_formatted": format_file_size(total_size)
        }
        
        return stats
    except dropbox.exceptions.ApiError as err:
        print(f"Error getting stats for {path}: {err}")
        return {"error": str(err)}

def list_team_members(team_dbx):
    """List all members in the Dropbox team."""
    try:
        members = team_dbx.team_members_list().members
        print("\nTeam Members:")
        for i, member in enumerate(members):
            profile = member.profile
            print(f"{i+1}. {profile.name.display_name} ({profile.email})")
        return members
    except Exception as e:
        print(f"Error listing team members: {e}")
        return []

def select_team_member(team_dbx):
    """List team members and let user select one."""
    members = list_team_members(team_dbx)
    
    if not members:
        print("No team members found or error occurred.")
        return None
    
    try:
        choice = int(input("\nEnter the number of the team member to explore (or 0 to exit): "))
        if choice == 0:
            return None
        if 1 <= choice <= len(members):
            selected_member = members[choice-1]
            member_id = selected_member.profile.team_member_id
            print(f"Selected: {selected_member.profile.name.display_name}")
            return team_dbx.as_user(member_id)
        else:
            print("Invalid selection.")
            return select_team_member(team_dbx)
    except ValueError:
        print("Please enter a valid number.")
        return select_team_member(team_dbx)

def interactive_explorer(dbx, current_path=""):
    """Interactive explorer for navigating Dropbox folders."""
    while True:
        # Clear screen (optional)
        os.system('cls' if os.name == 'nt' else 'clear')
        
        # Show current path
        print(f"\nCurrent path: {current_path or '/'}")
        
        # Get quick stats
        stats = get_folder_stats(dbx, current_path)
        print(f"Contents: {stats.get('folders', 0)} folders, {stats.get('files', 0)} files, {stats.get('total_size_formatted', '0 B')}")
        
        # List contents
        print("\nContents:")
        folders, files = list_folder_contents(dbx, current_path)
        
        # Show options
        print("\nOptions:")
        print("  cd <number> - Open folder by number")
        print("  cd .. - Go up one level")
        print("  cd <name> - Open folder by name")
        print("  stats - Show detailed statistics for this folder")
        print("  exit - Exit explorer")
        
        # Get command
        cmd = input("\nEnter command: ").strip()
        
        if cmd.lower() == "exit":
            break
        
        elif cmd.lower() == "stats":
            # Show detailed stats
            detailed_stats = get_detailed_stats(dbx, current_path)
            print("\nDetailed Statistics:")
            print(f"Total Folders: {detailed_stats['total_folders']}")
            print(f"Total Files: {detailed_stats['total_files']}")
            print(f"Total Size: {detailed_stats['total_size_formatted']}")
            
            print("\nFile Types:")
            for ext, count in sorted(detailed_stats['file_types'].items(), key=lambda x: x[1], reverse=True)[:10]:
                print(f"  {ext}: {count} files")
            
            print("\nLargest Files:")
            for file in detailed_stats['largest_files'][:5]:
                print(f"  {file['name']} ({file['size_formatted']})")
            
            input("\nPress Enter to continue...")
            
        elif cmd.startswith("cd "):
            target = cmd[3:].strip()
            
            # Go up one level
            if target == "..":
                if current_path:
                    current_path = os.path.dirname(current_path)
                continue
            
            # Try to navigate by number
            try:
                index = int(target) - 1
                if 0 <= index < len(folders):
                    current_path = folders[index].path_lower
                else:
                    print("Invalid folder number.")
                    input("Press Enter to continue...")
            except ValueError:
                # Try to navigate by name
                found = False
                for folder in folders:
                    if folder.name.lower() == target.lower():
                        current_path = folder.path_lower
                        found = True
                        break
                
                if not found:
                    print(f"Folder '{target}' not found.")
                    input("Press Enter to continue...")

def get_detailed_stats(dbx, path=""):
    """Get detailed statistics for a folder."""
    from collections import Counter
    
    stats = {
        "total_folders": 0,
        "total_files": 0,
        "total_size": 0,
        "file_types": Counter(),
        "largest_files": []
    }
    
    folders_to_process = [path]
    processed_count = 0
    
    print("Analyzing folder structure (this may take a moment)...")
    
    while folders_to_process and processed_count < 1000:  # Limit to prevent too long processing
        current_folder = folders_to_process.pop(0)
        processed_count += 1
        
        try:
            entries = dbx.files_list_folder(current_folder).entries
            
            for entry in entries:
                if isinstance(entry, dropbox.files.FolderMetadata):
                    stats["total_folders"] += 1
                    folders_to_process.append(entry.path_lower)
                elif isinstance(entry, dropbox.files.FileMetadata):
                    stats["total_files"] += 1
                    stats["total_size"] += entry.size
                    
                    # Count file types
                    file_ext = os.path.splitext(entry.name.lower())[1]
                    if file_ext:
                        stats["file_types"][file_ext] += 1
                    else:
                        stats["file_types"]["no_extension"] += 1
                    
                    # Track largest files
                    file_info = {
                        "name": entry.name,
                        "path": entry.path_display,
                        "size": entry.size,
                        "size_formatted": format_file_size(entry.size)
                    }
                    
                    stats["largest_files"].append(file_info)
                    stats["largest_files"] = sorted(stats["largest_files"], 
                                                   key=lambda x: x["size"], 
                                                   reverse=True)[:10]
                    
        except dropbox.exceptions.ApiError as err:
            print(f"Error accessing {current_folder}: {err}")
    
    if processed_count >= 1000:
        print("Note: Analysis limited to 1000 folders to prevent timeout.")
    
    stats["file_types"] = dict(stats["file_types"])
    stats["total_size_formatted"] = format_file_size(stats["total_size"])
    
    return stats

def main():
    print("Connecting to Dropbox...")
    try:
        # Try to create a team client first
        try:
            team_dbx = dropbox.DropboxTeam(
                app_key=DROPBOX_APP_KEY,
                app_secret=DROPBOX_APP_SECRET,
                oauth2_refresh_token=DROPBOX_REFRESH_TOKEN
            )
            
            # List team members and let user select one
            user_client = select_team_member(team_dbx)
            if not user_client:
                print("No user selected. Exiting.")
                return
                
            # Get account information to verify connection
            account = user_client.users_get_current_account()
            print(f"Connected to Dropbox account: {account.name.display_name}")
            
            # Start interactive explorer
            interactive_explorer(user_client)
            
        except Exception as e:
            print(f"Team access failed, trying individual access: {e}")
            # Fall back to individual access
            dbx = dropbox.Dropbox(
                app_key=DROPBOX_APP_KEY,
                app_secret=DROPBOX_APP_SECRET,
                oauth2_refresh_token=DROPBOX_REFRESH_TOKEN
            )
            account = dbx.users_get_current_account()
            print(f"Connected to Dropbox account: {account.name.display_name}")
            
            # Start interactive explorer
            interactive_explorer(dbx)
            
    except dropbox.exceptions.AuthError as e:
        print(f"Authentication error: {e}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()