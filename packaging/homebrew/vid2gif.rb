class Vid2gif < Formula
  desc "Convert videos and links (X, YouTube...) to GIFs from the Finder or the CLI"
  homepage "https://github.com/jbsaintebeuve/video-to-gif"
  url "https://github.com/jbsaintebeuve/video-to-gif/archive/refs/tags/v@VERSION@.tar.gz"
  sha256 "@SHA256@"
  license "MIT"
  head "https://github.com/jbsaintebeuve/video-to-gif.git", branch: "main"

  depends_on "ffmpeg"
  depends_on "python@3.15"
  depends_on "yt-dlp"

  def install
    libexec.install "vid2gif"
    python = formula_opt_bin("python@3.15")/"python3.15"
    # -P : le dossier courant ne peut pas masquer le module ; -s : ignore le site utilisateur.
    (bin/"vid2gif").write <<~SH
      #!/bin/sh
      export PYTHONPATH="#{libexec}"
      export VID2GIF_EXE="#{opt_bin}/vid2gif"
      exec "#{python}" -P -s -m vid2gif "$@"
    SH
  end

  def caveats
    <<~EOS
      Pour ajouter le clic droit « Convertir en GIF » dans le Finder
      et le raccourci ⌃⌥⌘G (lien vidéo copié → GIF), lancez une fois :
        vid2gif setup
    EOS
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/vid2gif --version")
    system formula_opt_bin("ffmpeg")/"ffmpeg", "-loglevel", "error", "-f", "lavfi",
           "-i", "testsrc2=duration=1:size=320x180:rate=10", "-pix_fmt", "yuv420p", testpath/"clip.mp4"
    system bin/"vid2gif", testpath/"clip.mp4", "-w", "160"
    assert_equal "GIF89a", (testpath/"clip.gif").binread(6)
  end
end
