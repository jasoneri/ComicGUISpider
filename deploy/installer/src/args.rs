use clap::Parser;

#[derive(Debug, Clone, Parser)]
#[command(name = "installer", version, about = "ComicGUISpider native updater")]
pub struct CliArgs {
    #[arg(long = "uv-exc")]
    pub uv_exc: String,

    #[arg(long = "cgs-ver")]
    pub cgs_ver: String,

    #[arg(long = "index-url", default_value_t)]
    pub index_url: String,

    #[arg(long = "parent-pid", default_value_t = 0)]
    pub parent_pid: u32,

    #[arg(long = "uv-tool-dir", default_value_t)]
    pub uv_tool_dir: String,

    #[arg(long = "uv-tool-bin-dir", default_value_t)]
    pub uv_tool_bin_dir: String,

    #[arg(long = "no-gui")]
    pub no_gui: bool,

    #[arg(long)]
    pub script: bool,

    #[arg(last = true, value_name = "UV_ARGS", allow_hyphen_values = true)]
    pub uv_args: Vec<String>,
}
