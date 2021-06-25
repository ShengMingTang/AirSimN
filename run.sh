# ! set variable
. ./config.sh
# ? $@: all args
# ? $1: setting.json path
# ! look up all ports in use
# ? sudo lsof -i -P -n | grep LISTEN | grep username
PROJECT_DIR=$PWD

UNREAL_ENV='AirSimNH'
UE4_PROJECT_ROOT="$UNREAL_ENV/LinuxNoEditor/"
echo "Using Unreal Env as $UNREAL_ENV"

if ! [ -d "$1" ]; then
    echo "settings.json path not set, leave as it is"
else
    echo "Use settings in $1"
    cp $1 $HOME/Documents/AirSim/settings.json
fi

# output surpressed
"$UE4_PROJECT_ROOT/$UNREAL_ENV/Binaries/Linux/$UNREAL_ENV" -windowed >/dev/null &
unreal_pid=$!
echo $unreal_pid


cd $NS3
./waf --run scratch/network/network > "$PROJECT_DIR/log/network.log" &
ns_pid=$!
cd -

sleep 3
cd application
python3 main.py > "$PROJECT_DIR/log/application.log"
app_pid=$!
cd -

# kill $ns_pid
kill $unreal_pid