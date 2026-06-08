def test_mcp_server_imports_and_exposes_entrypoint():
    from jkg.mcp_server import main, mcp

    assert callable(main)
    assert mcp.name == "jkg"

