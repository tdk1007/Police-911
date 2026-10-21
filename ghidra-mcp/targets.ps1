# Headless GhidraMCP targets. Paths are relative to the repo root.
# Ports must match .mcp.json.
$Targets = @{
    # Police 911 arcade (Konami PowerPC) main-RAM dump, existing analyzed project.
    arcade = @{
        Port = 8091; Binary = 'extracted\arcade\p911ud_ram_sensorbad.bin'
        Project = 'extracted\arcade\ghidra_proj'; ProjectName = 'arcade'
        Extra = @('--no-analyze')
    }
    # Police 24/7 PS2 EE executable, analyzed with ghidra-emotionengine-reloaded (MMI decodes).
    ps2 = @{
        Port = 8092; Binary = 'extracted\SLES_502.85'
        Project = 'extracted\ps2_ghidra_proj'; ProjectName = 'police247'
        Extra = @('--language', 'r5900:LE:32:default')
    }
}
