import os
from torf import Torrent

def create_torrent(input_path, output_dir, trackers=None, web_seeds=None, private=True, source="", comment="", piece_size=None, progress_callback=None):
    """
    Generate a .torrent file from a directory or file using torf.
    """
    if progress_callback:
        progress_callback({"type": "torrent_start", "message": "Initializing torrent..."})

    t = Torrent(path=input_path,
                trackers=trackers,
                webseeds=web_seeds,
                private=private,
                source=source,
                comment=comment)
    
    if piece_size:
        t.piece_size = piece_size
        
    if progress_callback:
        progress_callback({"type": "torrent_progress", "message": "Hashing pieces..."})
        
    def callback(torrent, path, pieces_done, total_pieces):
        if progress_callback and total_pieces > 0:
            percent = (pieces_done / total_pieces) * 100
            progress_callback({
                "type": "torrent_progress", 
                "message": f"Hashing pieces: {percent:.1f}%",
                "percent": percent
            })

    t.generate(callback=callback)
    
    output_filename = f"{os.path.basename(os.path.abspath(input_path))}.torrent"
    output_path = os.path.join(output_dir, output_filename)
    
    t.write(output_path)
    
    if progress_callback:
        progress_callback({"type": "torrent_done", "message": "Torrent created", "output": output_filename})
        
    return output_path
