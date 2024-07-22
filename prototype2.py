import requests
import json
import time
import random
import sys
import os
import tkinter as tk
from tkinter import filedialog, messagebox
import PyPDF2
import docx
import pickle
from datetime import datetime
import concurrent.futures

global_context = ""
file_inspection_mode = False
uploaded_files_context = ""


def generate_text(prompt, model_name="llama3"):
    global global_context, file_inspection_mode, uploaded_files_context
    url = "http://localhost:11434/api/generate"

    if file_inspection_mode:
        if not uploaded_files_context:
            return "No files have been uploaded yet. Please use the '/scan' command to add files to the knowledge base."
        system_context = uploaded_files_context
    else:
        system_context = global_context

    data = {
        "model": model_name,
        "prompt": prompt,
        "system": system_context
    }
    try:
        model_response = requests.post(url, json=data, stream=True)
        model_response.raise_for_status()
        return model_response
    except requests.RequestException as e:
        return f"Error: {e}"


def process_stream(model_response):
    result = ""
    buffer = ""
    last_print_time = time.time()
    for line in model_response.iter_lines():
        if line:
            try:
                decoded_line = line.decode('utf-8')
                response_data = json.loads(decoded_line)
                if 'response' in response_data:
                    chunk = response_data['response']
                    result += chunk
                    buffer += chunk
                    current_time = time.time()
                    if current_time - last_print_time > 0.05 or len(buffer) > 10:
                        print_chunk = buffer[:random.randint(1, len(buffer))]
                        sys.stdout.write(print_chunk)
                        sys.stdout.flush()
                        buffer = buffer[len(print_chunk):]
                        last_print_time = current_time
                        time.sleep(0.01)
            except json.JSONDecodeError:
                print(f"Error decoding JSON: {decoded_line}")
    if buffer:
        sys.stdout.write(buffer)
        sys.stdout.flush()
    print()
    return result


def input_thread(prompt):
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        return "/bye"


def select_files():
    root = tk.Tk()
    root.withdraw()
    file_types = [
        ("Text files", "*.txt"),
        ("PDF files", "*.pdf"),
        ("Word documents", "*.docx"),
        ("Markdown files", "*.md"),
        ("Python files", "*.py"),
        ("JavaScript files", "*.js"),
        ("HTML files", "*.html"),
        ("CSS files", "*.css"),
        ("All files", "*.*")
    ]
    files = filedialog.askopenfilenames(
        title="Select files for knowledge base",
        filetypes=file_types
    )
    return list(files) if files else None


def read_file_content(file_path):
    file_extension = os.path.splitext(file_path)[1].lower()
    try:
        if file_extension in ['.txt', '.md', '.py', '.js', '.html', '.css']:
            with open(file_path, 'r', encoding='utf-8') as file:
                return file.read()
        elif file_extension == '.pdf':
            content = ""
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for page in pdf_reader.pages:
                    content += page.extract_text() + "\n"
            return content
        elif file_extension == '.docx':
            doc = docx.Document(file_path)
            return "\n".join([paragraph.text for paragraph in doc.paragraphs])
        else:
            with open(file_path, 'r', encoding='utf-8') as file:
                return file.read()
    except Exception as e:
        return f"Unable to read file {file_path}: {str(e)}"


def save_knowledge_base(knowledge_content):
    with open('knowledge_base.pkl', 'wb') as f:
        pickle.dump(knowledge_content, f)


def load_knowledge_base():
    try:
        with open('knowledge_base.pkl', 'rb') as f:
            return pickle.load(f)
    except FileNotFoundError:
        return ""


def create_file_summary(file_path, content):
    file_name = os.path.basename(file_path)
    file_type = os.path.splitext(file_name)[1]
    creation_time = datetime.fromtimestamp(os.path.getctime(file_path))

    summary_prompt = f"Summarize the following content in 2-3 sentences:\n\n{content[:1000]}..."
    summary_response = generate_text(summary_prompt)
    summary = process_stream(summary_response) if not isinstance(summary_response, str) else summary_response

    return f"File: {file_name}\nType: {file_type}\nCreated: {creation_time}\nSummary: {summary}\n\n{content}\n\n"


def create_knowledge_base(files):
    global uploaded_files_context
    new_knowledge = ""

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_to_file = {executor.submit(read_file_content, file): file for file in files}
        for future in concurrent.futures.as_completed(future_to_file):
            file = future_to_file[future]
            content = future.result()
            new_knowledge += create_file_summary(file, content)

    uploaded_files_context = (
        f"You are an AI assistant with knowledge of the following files:\n\n"
        f"{new_knowledge}\n\nUse this information to assist with answering questions."
    )
    save_knowledge_base(uploaded_files_context)
    return uploaded_files_context


def prepare_context(model_name):
    global global_context
    knowledge_content = load_knowledge_base()
    global_context = (
        f"You are an AI assistant with access to your pretrained knowledge and the following additional files:\n\n"
        f"{knowledge_content}\n\nUse this information to assist with answering questions."
    )
    print(f"Knowledge base loaded. Using model: {model_name} with added context.")
    return model_name


def remove_files_from_knowledge_base():
    global uploaded_files_context
    files = uploaded_files_context.split("File: ")
    files = [f.strip() for f in files if f.strip()]

    if not files:
        print("No files in the knowledge base.")
        return False

    root = tk.Tk()
    root.withdraw()

    file_list = tk.Toplevel(root)
    file_list.title("Select files to remove")
    file_list.geometry("400x300")

    listbox = tk.Listbox(file_list, selectmode=tk.MULTIPLE)
    listbox.pack(expand=True, fill=tk.BOTH)

    for file in files:
        listbox.insert(tk.END, file.split("\n")[0])

    files_removed = False

    def remove_selected():
        nonlocal files_removed
        selected_indices = listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("No Selection", "Please select files to remove.")
            return

        new_knowledge_content = ""
        for i, uploaded_file in enumerate(files):
            if i not in selected_indices:
                new_knowledge_content += f"File: {uploaded_file}"

        uploaded_files_context = (
            f"You are an AI assistant with knowledge of the following files:\n\n"
            f"{new_knowledge_content}\n\nUse this information to assist with answering questions."
        )
        save_knowledge_base(uploaded_files_context)
        print(f"Removed {len(selected_indices)} file(s) from the knowledge base.")
        files_removed = True
        file_list.destroy()
        root.quit()

    remove_button = tk.Button(file_list, text="Remove Selected", command=remove_selected)
    remove_button.pack()

    root.mainloop()
    return files_removed


def main():
    global file_inspection_mode, uploaded_files_context
    print("Type your prompts and press Enter to send them.")
    print("To exit, press Ctrl+C, Ctrl+D, or type '/bye'.")
    print("To enter file inspection mode, type 'fileinspect_on'.")
    print("To exit file inspection mode, type 'fileinspect_off'.")

    current_model = "llama3"
    current_model = prepare_context(current_model)

    try:
        while True:
            user_prompt = input_thread("\nEnter your prompt: ")

            if user_prompt.lower() == "/bye":
                print("Goodbye!")
                break
            elif user_prompt.lower() == "fileinspect_on":
                file_inspection_mode = True
                print("File inspection mode activated. The model will only access uploaded files.")
                print("You can now use '/scan' to add files and '/remove' to remove files.")
                continue
            elif user_prompt.lower() == "fileinspect_off":
                file_inspection_mode = False
                uploaded_files_context = ""
                save_knowledge_base("")
                print("File inspection mode deactivated. The model can now access its pretrained data.")
                print("All uploaded files have been removed from the knowledge base.")
                continue
            elif user_prompt.lower() == "/scan":
                if not file_inspection_mode:
                    print("Error: '/scan' can only be used in file inspection mode. Type 'fileinspect_on' to activate.")
                    continue
                selected_files = select_files()
                if selected_files:
                    print(f"Selected {len(selected_files)} file(s).")
                    create_knowledge_base(selected_files)
                    print("Files added to the knowledge base.")
                else:
                    print("No files selected.")
                continue
            elif user_prompt.lower() == "/remove":
                if not file_inspection_mode:
                    print(
                        "Error: '/remove' can only be used in file inspection mode. Type 'fileinspect_on' to activate.")
                    continue
                remove_files_from_knowledge_base()
                continue

            print()
            response = generate_text(user_prompt, current_model)

            if isinstance(response, str):
                print(response)
            else:
                process_stream(response)

    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    main()
