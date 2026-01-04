import os
import subprocess
import shutil
from pathlib import Path
import logging

class LaTeXCompiler:
    def __init__(self, output_dir):
        self.output_dir = Path(output_dir)
        self.cache_dir = self.output_dir / ".cache"
        
        # Set up logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
    
    def find_latex_files(self):
        """Find all .tex files in the output directory recursively."""
        tex_files = []
        for tex_file in self.output_dir.rglob("*.tex"):
            # Skip files in the cache directory
            if not str(tex_file).startswith(str(self.cache_dir)):
                tex_files.append(tex_file)
        
        self.logger.info(f"Found {len(tex_files)} LaTeX files to compile")
        return tex_files
    
    def create_cache_directory(self, tex_file):
        """Create a unique cache directory for each tex file."""
        # Create a unique directory name based on the relative path
        relative_path = tex_file.relative_to(self.output_dir)
        cache_subdir = self.cache_dir / relative_path.parent / relative_path.stem
        cache_subdir.mkdir(parents=True, exist_ok=True)
        return cache_subdir
    
    def copy_source_directory(self, tex_file, cache_dir):
        """Copy the entire source directory to cache to preserve relative paths."""
        source_dir = tex_file.parent
        
        # Copy all files from source directory to cache directory
        for item in source_dir.iterdir():
            if item.is_file():
                dest_file = cache_dir / item.name
                try:
                    shutil.copy2(item, dest_file)
                except Exception as e:
                    self.logger.warning(f"Could not copy {item.name}: {str(e)}")
            elif item.is_dir() and item.name != ".cache":
                # Copy subdirectories but avoid copying cache directories
                dest_dir = cache_dir / item.name
                try:
                    shutil.copytree(item, dest_dir, ignore=shutil.ignore_patterns('.cache'))
                except Exception as e:
                    self.logger.warning(f"Could not copy directory {item.name}: {str(e)}")
        
        return cache_dir / tex_file.name
    
    def compile_latex(self, tex_file, cache_dir):
        """Compile a single LaTeX file using pdflatex."""
        self.logger.info(f"Compiling {tex_file.name}...")
        
        # Copy source directory to cache to preserve relative paths
        cached_tex_file = self.copy_source_directory(tex_file, cache_dir)
        
        if not cached_tex_file.exists():
            self.logger.error(f"Failed to copy {tex_file.name} to cache directory")
            return None
        
        # pdflatex command - run in the cache directory without output-directory flag
        cmd = [
            "pdflatex",
            "-interaction=nonstopmode",  # Don't stop on errors
            "-halt-on-error",           # But halt on major errors
            cached_tex_file.name        # Input file (just filename since we're in the right directory)
        ]
        
        compilation_logs = []
        pdf_file = cache_dir / f"{tex_file.stem}.pdf"
        
        # Run pdflatex multiple times to resolve cross-references and bibliography
        for attempt in range(3):
            try:
                self.logger.info(f"Running pdflatex (attempt {attempt + 1}/3) for {tex_file.name}")
                
                print(f"Running command: {' '.join(cmd)}")
                result = subprocess.run(
                    cmd,
                    cwd=cache_dir,  # Run from cache directory
                    capture_output=True,
                    text=True,
                    timeout=3000  # 50 minute timeout
                )
                
                # Log this attempt
                compilation_logs.append(f"=== ATTEMPT {attempt + 1} ===\n")
                compilation_logs.append(f"Command: {' '.join(cmd)}\n")
                compilation_logs.append(f"Return code: {result.returncode}\n")
                compilation_logs.append("STDOUT:\n")
                compilation_logs.append(result.stdout)
                compilation_logs.append("\nSTDERR:\n")
                compilation_logs.append(result.stderr)
                compilation_logs.append("\n" + "="*50 + "\n\n")
                
                # Check if PDF exists and has content
                if pdf_file.exists() and pdf_file.stat().st_size > 0:
                    self.logger.info(f"PDF generated successfully for {tex_file.name} (size: {pdf_file.stat().st_size} bytes)")
                    break
                elif result.returncode == 0:
                    # pdflatex reported success but no PDF or empty PDF
                    self.logger.warning(f"pdflatex completed but PDF is missing or empty for {tex_file.name}")
                else:
                    self.logger.warning(f"pdflatex failed with return code {result.returncode} for {tex_file.name}")
                
                # If this is the last attempt and still no valid PDF, log more details
                if attempt == 2:
                    if not pdf_file.exists():
                        self.logger.error(f"No PDF file generated for {tex_file.name}")
                    elif pdf_file.stat().st_size == 0:
                        self.logger.error(f"Empty PDF file generated for {tex_file.name}")
                        
            except subprocess.TimeoutExpired:
                self.logger.error(f"Compilation timeout for {tex_file.name}")
                compilation_logs.append(f"TIMEOUT after 3000 seconds\n")
            except Exception as e:
                self.logger.error(f"Error compiling {tex_file.name}: {str(e)}")
                compilation_logs.append(f"EXCEPTION: {str(e)}\n")
            
        # Save comprehensive compilation log
        log_file = cache_dir / f"{tex_file.stem}_compilation.log"
        with open(log_file, 'w', encoding='utf-8') as f:
            f.writelines(compilation_logs)
        
        # Also save the LaTeX log file if it exists
        latex_log = cache_dir / f"{tex_file.stem}.log"
        if latex_log.exists():
            saved_latex_log = cache_dir / f"{tex_file.stem}_pdflatex.log"
            shutil.copy2(latex_log, saved_latex_log)
        
        # Return PDF file if it exists and has content
        if pdf_file.exists() and pdf_file.stat().st_size > 0:
            return pdf_file
        else:
            return None
    
    def move_pdf_to_source_location(self, pdf_file, tex_file):
        """Move the compiled PDF to the same directory as the source .tex file."""
        if pdf_file and pdf_file.exists():
            destination = tex_file.parent / pdf_file.name
            try:
                # If destination already exists, remove it first
                if destination.exists():
                    destination.unlink()
                shutil.move(str(pdf_file), str(destination))
                self.logger.info(f"Moved {pdf_file.name} to {destination.parent}")
                return destination
            except Exception as e:
                self.logger.error(f"Error moving PDF file: {str(e)}")
                return None
        return None
    
    def validate_latex_environment(self):
        """Check if pdflatex is available in the system."""
        try:
            result = subprocess.run(
                ["pdflatex", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                self.logger.info("pdflatex is available")
                return True
            else:
                self.logger.error("pdflatex is not working properly")
                return False
        except Exception as e:
            self.logger.error(f"pdflatex is not available: {str(e)}")
            return False
    
    def compile_all(self):
        """Main method to compile all LaTeX files found in the output directory."""
        self.logger.info("Starting LaTeX compilation process...")
        
        # Validate LaTeX environment
        if not self.validate_latex_environment():
            self.logger.error("Cannot proceed without pdflatex. Please install LaTeX distribution.")
            return
        
        # Ensure cache directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Find all LaTeX files
        tex_files = self.find_latex_files()
        
        if not tex_files:
            self.logger.info("No LaTeX files found to compile")
            return
        
        compiled_count = 0
        failed_count = 0
        
        # Compile each file
        for tex_file in tex_files:
            try:
                self.logger.info(f"Processing {tex_file.relative_to(self.output_dir)}")
                
                # Create cache directory for this file
                cache_dir = self.create_cache_directory(tex_file)
                
                # Compile the LaTeX file
                pdf_file = self.compile_latex(tex_file, cache_dir)
                
                if pdf_file:
                    # Move PDF to source location
                    final_pdf = self.move_pdf_to_source_location(pdf_file, tex_file)
                    if final_pdf:
                        compiled_count += 1
                        self.logger.info(f"✓ Successfully compiled {tex_file.name}")
                    else:
                        failed_count += 1
                        self.logger.error(f"✗ Failed to move PDF for {tex_file.name}")
                else:
                    failed_count += 1
                    self.logger.error(f"✗ Failed to compile {tex_file.name}")
                    
            except Exception as e:
                self.logger.error(f"Unexpected error processing {tex_file}: {str(e)}")
                failed_count += 1
        
        # Summary
        self.logger.info(f"Compilation complete! Successfully compiled: {compiled_count}, Failed: {failed_count}")
        self.logger.info(f"Log files are stored in: {self.cache_dir}")
        
        if failed_count > 0:
            self.logger.info("Check the compilation logs in the cache directory for details on failed compilations")

# Example usage:
if __name__ == "__main__":
    output_directory = "/home/ubuntu/EduAgents/exp/30dm"
    compiler = LaTeXCompiler(output_directory)
    compiler.compile_all()