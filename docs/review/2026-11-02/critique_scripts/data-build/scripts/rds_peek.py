import sys, warnings
warnings.filterwarnings("ignore")
import rdata, pandas as pd
print("rdata", rdata.__version__ if hasattr(rdata,"__version__") else "?")
p = sys.argv[1]
parsed = rdata.parser.parse_file(p)
df = rdata.conversion.convert(parsed)
print(type(df)); print(df.dtypes); print(df.head(3).to_string())
print(df["CSR_TIMESTAMP_BEGIN"].head(3).tolist())
t = pd.to_datetime(df["CSR_TIMESTAMP_BEGIN"], unit="s", errors="coerce")
print(t.head(3).tolist(), t.isna().sum())
