# ! This will extrat all the compressed file then compile
echo "Make sure that you have built Unreal Engine and AirSim correctly"
echo "If not, follow this link: https://microsoft.github.io/AirSim/build_linux.html"

. ./config.sh
if [ -d $NS ] 
then
    echo "NS3 directory exists, no decompression." 
else
    echo "NS3 directory does not exists, decompress "
    tar xjf compressed/ns-allinone-3.32.tar.bz2
fi

# patching wscript to fit our need
diff -u $NS3/wscript wscript > wscript.patch
patch $NS3/wscript wscript.patch
rm wscript.patch

# create symbolic link so that we can modify files at root
if [! -e $NS3/scratch/network ] 
then
    echo "create symbolic link to application so that we can modify files at root"
    ln -s ../../../network $NS3/scratch/network
fi

cd $NS3

# configure
./waf configure

# build
echo "Start building, this may take some time"
./waf

# extract environment
# https://github.com/microsoft/AirSim/releases/tag/v1.5.0-linux
# Choose AirSimNH and extract it to the current folder
# unzip compressed/AirSimNH.zip